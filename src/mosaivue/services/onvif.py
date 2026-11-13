"""Bounded ONVIF Media1 discovery at a user-supplied device endpoint.

Only read operations are sent to the camera. Network multicast discovery,
Media2-only devices, PTZ, and changes to the camera's encoder are not implemented.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import math
import secrets
from datetime import UTC, datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import httpx
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from ..schemas import CameraCreate, StreamProfileIn
from ..schemas_onvif import (
    OnvifConnection,
    OnvifImport,
    OnvifProfile,
    OnvifProfiles,
    validate_device_url,
)
from ..security import strip_url_credentials

SOAP = "http://www.w3.org/2003/05/soap-envelope"
DEVICE = "http://www.onvif.org/ver10/device/wsdl"
MEDIA = "http://www.onvif.org/ver10/media/wsdl"
SCHEMA = "http://www.onvif.org/ver10/schema"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
PASSWORD_DIGEST = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
BASE64_BINARY = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
MAX_XML_BYTES = 1024 * 1024
MAX_PROFILES = 32
REQUEST_TIMEOUT = 6.0
OPERATION_TIMEOUT = 45.0


class OnvifError(ValueError):
    """A safe, credential-free error suitable for display in the control UI."""


def _element(parent: ET.Element, namespace: str, name: str, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, f"{{{namespace}}}{name}")
    element.text = text
    return element


def _envelope(operation: ET.Element, username: str, password: str) -> bytes:
    envelope = ET.Element(f"{{{SOAP}}}Envelope")
    if username:
        header = _element(envelope, SOAP, "Header")
        security = _element(header, WSSE, "Security")
        security.set(f"{{{SOAP}}}mustUnderstand", "true")
        token = _element(security, WSSE, "UsernameToken")
        nonce = secrets.token_bytes(20)
        created = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        # SHA-1 here is mandated by the WS-Security UsernameToken wire protocol.
        digest = hashlib.sha1(nonce + created.encode() + password.encode()).digest()  # nosec B324
        _element(token, WSSE, "Username", username)
        _element(token, WSSE, "Password", base64.b64encode(digest).decode()).set("Type", PASSWORD_DIGEST)
        _element(token, WSSE, "Nonce", base64.b64encode(nonce).decode()).set("EncodingType", BASE64_BINARY)
        _element(token, WSU, "Created", created)
    _element(envelope, SOAP, "Body").append(operation)
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def _parse_xml(body: bytes, operation: str) -> ET.Element:
    if len(body) > MAX_XML_BYTES:
        raise OnvifError("ONVIF response exceeds the 1 MiB limit")
    try:
        root = SafeET.fromstring(body, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise OnvifError("ONVIF response contains an unsupported XML declaration") from exc
    except (ET.ParseError, ValueError) as exc:
        raise OnvifError("Device returned invalid ONVIF XML") from exc
    fault = root.find(".//{*}Fault")
    if fault is not None:
        values = " ".join(fault.itertext()).lower()
        if any(value in values for value in ("notauthorized", "unauthorized", "authentication", "security")):
            raise OnvifError("ONVIF authentication failed; check credentials and camera time synchronization")
        raise OnvifError(f"Camera rejected ONVIF {operation}; check Media1 support")
    response = root.find(f".//{{*}}{operation}Response")
    if response is None:
        raise OnvifError(f"Device did not return an ONVIF {operation} response")
    return response


def _text(element: ET.Element, path: str) -> str:
    return (element.findtext(path) or "").strip()


def _number(element: ET.Element, path: str, maximum: float, *, integer: bool = True) -> int | float | None:
    try:
        value = float(_text(element, path))
        if not math.isfinite(value) or value <= 0 or value > maximum:
            return None
        return int(value) if integer else value
    except ValueError:
        return None


def _same_device_url(candidate: str, device_url: str, *, stream: bool = False) -> str:
    try:
        validated = StreamProfileIn(url=candidate).url if stream else validate_device_url(candidate)
        original = urlsplit(device_url)
        target = urlsplit(validated)
        def host(value: str | None) -> str:
            value = (value or "").lower().rstrip(".")
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                return value
        if host(target.hostname) != host(original.hostname):
            raise ValueError("different host")
        if not stream and original.scheme == "https" and target.scheme != "https":
            raise ValueError("TLS downgrade")
    except ValueError as exc:
        raise OnvifError(
            "Camera advertised an invalid endpoint, another host, or an insecure service downgrade; "
            "configure its advertised address or add its RTSP URL manually"
        ) from exc
    return validated


class OnvifClient:
    def __init__(self, client: httpx.AsyncClient, connection: OnvifConnection):
        self.client = client
        self.connection = connection

    async def _request(self, url: str, namespace: str, operation: ET.Element) -> ET.Element:
        name = operation.tag.rsplit("}", 1)[-1]
        action = f"{namespace}/{name}"
        password = self.connection.password.get_secret_value()
        content = _envelope(operation, self.connection.username, password)
        headers = {
            "Content-Type": f'application/soap+xml; charset=utf-8; action="{action}"',
            "SOAPAction": f'"{action}"',
            "Accept": "application/soap+xml, application/xml, text/xml",
        }
        auth: httpx.Auth | None = None
        if self.connection.username:
            auth = httpx.DigestAuth(self.connection.username, password)
        for attempt in range(2):
            try:
                async with self.client.stream("POST", url, content=content, headers=headers, auth=auth) as response:
                    if response.status_code in {401, 403}:
                        challenge = response.headers.get("www-authenticate", "").lower()
                        if attempt == 0 and self.connection.username and "basic" in challenge and "digest" not in challenge:
                            auth = httpx.BasicAuth(self.connection.username, password)
                            continue
                        raise OnvifError("ONVIF authentication failed; check credentials and camera time synchronization")
                    if response.is_redirect:
                        raise OnvifError("ONVIF endpoint redirected; enter the camera's final device-service URL")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(chunks) + len(chunk) > MAX_XML_BYTES:
                            raise OnvifError("ONVIF response exceeds the 1 MiB limit")
                        chunks.extend(chunk)
                    if response.status_code >= 400 and not chunks:
                        raise OnvifError(f"ONVIF {name} failed with HTTP {response.status_code}")
                    parsed = _parse_xml(bytes(chunks), name)
                    if response.status_code >= 400:
                        raise OnvifError(f"ONVIF {name} failed with HTTP {response.status_code}")
                    return parsed
            except httpx.TimeoutException as exc:
                raise OnvifError("Camera did not answer ONVIF before the request timed out") from exc
            except httpx.HTTPError as exc:
                raise OnvifError("Cannot connect to ONVIF; check the device URL, network, and HTTPS certificate") from exc
            except (NotImplementedError, KeyError, ValueError) as exc:
                if isinstance(exc, OnvifError):
                    raise
                raise OnvifError("Camera uses an unsupported or malformed HTTP authentication challenge") from exc
        raise OnvifError("ONVIF authentication failed")

    async def list_profiles(self) -> tuple[str, OnvifProfiles]:
        operation = ET.Element(f"{{{DEVICE}}}GetCapabilities")
        _element(operation, DEVICE, "Category", "Media")
        capabilities = await self._request(self.connection.device_url, DEVICE, operation)
        media_url = _text(capabilities, ".//{*}Media/{*}XAddr")
        if not media_url:
            raise OnvifError("No ONVIF Media1 service was advertised; Media2-only cameras require manual RTSP setup")
        media_url = _same_device_url(media_url, self.connection.device_url)
        response = await self._request(media_url, MEDIA, ET.Element(f"{{{MEDIA}}}GetProfiles"))
        elements = response.findall("{*}Profiles")
        if len(elements) > MAX_PROFILES:
            raise OnvifError("Camera advertises more than 32 profiles; use manual RTSP setup for this device")
        profiles: list[OnvifProfile] = []
        warnings: list[str] = []
        seen: set[str] = set()
        names: set[str] = set()
        for item in elements:
            token = item.get("token", "")
            encoder = item.find("{*}VideoEncoderConfiguration")
            if not token or len(token) > 512 or token in seen or encoder is None:
                warnings.append("Skipped a duplicate, invalid, or non-video ONVIF profile")
                continue
            seen.add(token)
            name = _text(item, "{*}Name") or f"Profile {len(profiles) + 1}"
            base_name = name[:100]
            name = base_name
            suffix = 2
            while name in names:
                name = f"{base_name[:90]} ({suffix})"
                suffix += 1
            names.add(name)
            codec = _text(encoder, "{*}Encoding").upper()
            if codec not in {"H264", "H265", "JPEG", "MPEG4"}:
                warnings.append("Skipped a profile with an unsupported or missing video encoding")
                continue
            bitrate = _number(encoder, "{*}RateControl/{*}BitrateLimit", 1000000)
            profiles.append(OnvifProfile(
                token=token,
                name=name[:100],
                codec=codec,
                width=_number(encoder, "{*}Resolution/{*}Width", 16384),
                height=_number(encoder, "{*}Resolution/{*}Height", 16384),
                fps=_number(encoder, "{*}RateControl/{*}FrameRateLimit", 240, integer=False),
                bitrate=int(bitrate * 1000) if bitrate is not None else None,
            ))
        if not profiles:
            raise OnvifError("No supported video profiles were found on the ONVIF Media1 service")
        return media_url, OnvifProfiles(profiles=profiles, warnings=warnings)

    async def stream_uri(self, media_url: str, token: str) -> str:
        operation = ET.Element(f"{{{MEDIA}}}GetStreamUri")
        setup = _element(operation, MEDIA, "StreamSetup")
        _element(setup, SCHEMA, "Stream", "RTP-Unicast")
        transport = _element(setup, SCHEMA, "Transport")
        _element(transport, SCHEMA, "Protocol", "RTSP")
        _element(operation, MEDIA, "ProfileToken", token)
        response = await self._request(media_url, MEDIA, operation)
        uri = _text(response, ".//{*}Uri")
        return _same_device_url(uri, self.connection.device_url, stream=True)


def _client() -> httpx.AsyncClient:
    # A camera request must not inherit an appliance's external HTTP proxy.
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False, trust_env=False)


async def inspect_profiles(connection: OnvifConnection) -> OnvifProfiles:
    try:
        async with asyncio.timeout(OPERATION_TIMEOUT), _client() as client:
            _, profiles = await OnvifClient(client, connection).list_profiles()
            return profiles
    except TimeoutError as exc:
        raise OnvifError("ONVIF inspection timed out") from exc


async def camera_payload(connection: OnvifImport) -> CameraCreate:
    try:
        async with asyncio.timeout(OPERATION_TIMEOUT), _client() as client:
            onvif = OnvifClient(client, connection)
            media_url, result = await onvif.list_profiles()
            available = {profile.token: profile for profile in result.profiles}
            if any(token not in available for token in connection.profile_tokens):
                raise OnvifError("A selected profile no longer exists; inspect the camera again")
            profiles = []
            for priority, token in enumerate(connection.profile_tokens):
                metadata = available[token].model_dump(exclude={"token"})
                profiles.append(StreamProfileIn(
                    **metadata, url=await onvif.stream_uri(media_url, token), priority=priority,
                ))
            # A device may issue streaming credentials distinct from its ONVIF
            # account. Prefer that explicit media credential when it is shared
            # consistently by the selected profiles.
            embedded = {
                (username, password)
                for profile in profiles
                for _, username, password in [strip_url_credentials(profile.url)]
                if username is not None
            }
            if len(embedded) > 1:
                raise OnvifError("Selected profiles use different streaming credentials; import them as separate cameras")
            username, password = next(iter(embedded)) if embedded else (
                connection.username or None, connection.password.get_secret_value() or None,
            )
            return CameraCreate(
                name=connection.name,
                vendor="onvif",
                host=urlsplit(connection.device_url).hostname,
                username=username,
                password=password,
                stream_profiles=profiles,
            )
    except TimeoutError as exc:
        raise OnvifError("ONVIF import timed out; select fewer profiles and retry") from exc
