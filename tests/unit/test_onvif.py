from __future__ import annotations

import base64
import hashlib
from xml.etree import ElementTree as ET

import httpx
import pytest
from pydantic import ValidationError

from mosaivue.schemas_onvif import OnvifConnection, OnvifImport
from mosaivue.services import onvif

DEVICE_URL = "http://192.0.2.20/onvif/device_service"
MEDIA_URL = "http://192.0.2.20/onvif/media_service"


def soap(body: str) -> bytes:
    return (
        f'<s:Envelope xmlns:s="{onvif.SOAP}" xmlns:tds="{onvif.DEVICE}" '
        f'xmlns:trt="{onvif.MEDIA}" xmlns:tt="{onvif.SCHEMA}">'
        f"<s:Body>{body}</s:Body></s:Envelope>"
    ).encode()


def capabilities(media_url: str = MEDIA_URL) -> bytes:
    return soap(
        "<tds:GetCapabilitiesResponse><tds:Capabilities><tt:Media>"
        f"<tt:XAddr>{media_url}</tt:XAddr>"
        "</tt:Media></tds:Capabilities></tds:GetCapabilitiesResponse>"
    )


def profile(token: str = "main", name: str = "Main", codec: str = "H264") -> str:
    return (
        f'<trt:Profiles token="{token}"><tt:Name>{name}</tt:Name>'
        "<tt:VideoEncoderConfiguration>"
        f"<tt:Encoding>{codec}</tt:Encoding>"
        "<tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:Resolution>"
        "<tt:RateControl><tt:FrameRateLimit>25</tt:FrameRateLimit>"
        "<tt:BitrateLimit>4096</tt:BitrateLimit></tt:RateControl>"
        "</tt:VideoEncoderConfiguration></trt:Profiles>"
    )


def profiles_xml() -> bytes:
    return soap(f"<trt:GetProfilesResponse>{profile()}{profile('sub', 'Sub')}</trt:GetProfilesResponse>")


def device_handler(request: httpx.Request) -> httpx.Response:
    operation = ET.fromstring(request.content).find(f"{{{onvif.SOAP}}}Body")[0]
    name = operation.tag.rsplit("}", 1)[-1]
    if name == "GetCapabilities":
        return httpx.Response(200, content=capabilities())
    if name == "GetProfiles":
        return httpx.Response(200, content=profiles_xml())
    assert name == "GetStreamUri"
    assert operation.findtext(f"{{{onvif.MEDIA}}}StreamSetup/{{{onvif.SCHEMA}}}Stream") == "RTP-Unicast"
    assert operation.findtext(f"{{{onvif.MEDIA}}}StreamSetup/{{{onvif.SCHEMA}}}Transport/{{{onvif.SCHEMA}}}Protocol") == "RTSP"
    token = operation.findtext(f"{{{onvif.MEDIA}}}ProfileToken")
    return httpx.Response(200, content=soap(
        f"<trt:GetStreamUriResponse><trt:MediaUri><tt:Uri>rtsp://192.0.2.20/{token}</tt:Uri>"
        "</trt:MediaUri></trt:GetStreamUriResponse>"
    ))


def install_transport(monkeypatch, handler=device_handler) -> None:
    monkeypatch.setattr(onvif, "_client", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler), timeout=1, follow_redirects=False, trust_env=False,
    ))


@pytest.mark.asyncio
async def test_onvif_profiles_inspection_has_metadata_but_no_stream_uris(monkeypatch) -> None:
    install_transport(monkeypatch)
    result = await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL, username="viewer", password=" private "))
    assert [item.token for item in result.profiles] == ["main", "sub"]
    assert result.profiles[0].bitrate == 4096000
    assert result.profiles[0].width == 1920
    assert result.profiles[0].fps == 25
    assert "rtsp://" not in result.model_dump_json()
    assert "private" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_import_retains_selected_profiles_and_exact_password(monkeypatch) -> None:
    install_transport(monkeypatch)
    result = await onvif.camera_payload(OnvifImport(
        device_url=DEVICE_URL, username="viewer", password=" private ",
        name="Front Door", profile_tokens=["sub", "main"],
    ))
    assert result.password == " private "
    assert result.vendor == "onvif"
    assert [item.url for item in result.stream_profiles] == ["rtsp://192.0.2.20/sub", "rtsp://192.0.2.20/main"]
    assert [item.priority for item in result.stream_profiles] == [0, 1]


@pytest.mark.asyncio
async def test_import_rejects_stale_selection_before_stream_requests(monkeypatch) -> None:
    install_transport(monkeypatch)
    with pytest.raises(onvif.OnvifError, match="no longer exists"):
        await onvif.camera_payload(OnvifImport(device_url=DEVICE_URL, name="Camera", profile_tokens=["stale"]))


def test_username_token_uses_standard_password_digest_and_escapes_xml() -> None:
    payload = onvif._envelope(ET.Element(f"{{{onvif.MEDIA}}}GetProfiles"), "viewer<&", " private ")
    root = ET.fromstring(payload)
    token = root.find(f".//{{{onvif.WSSE}}}UsernameToken")
    nonce = base64.b64decode(token.findtext(f"{{{onvif.WSSE}}}Nonce"))
    created = token.findtext(f"{{{onvif.WSU}}}Created")
    digest = token.findtext(f"{{{onvif.WSSE}}}Password")
    assert digest == base64.b64encode(hashlib.sha1(nonce + created.encode() + b" private ").digest()).decode()
    assert token.findtext(f"{{{onvif.WSSE}}}Username") == "viewer<&"
    assert b" private " not in payload


@pytest.mark.parametrize("endpoint", [
    "file:///etc/passwd", "http://", "http://user:password@192.0.2.20/onvif", "http://192.0.2.20/#fragment",
    "http://192.0.2.20:70000/onvif", "http://192.0.2.20:0/onvif", "http://192.0.2.20/on vif",
])
def test_invalid_device_urls_rejected(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        OnvifConnection(device_url=endpoint)


@pytest.mark.parametrize("endpoint", ["http://192.0.2.20/onvif", "https://camera.local:8443/onvif", "http://[2001:db8::20]/onvif"])
def test_valid_device_urls_supported(endpoint: str) -> None:
    assert OnvifConnection(device_url=endpoint).device_url == endpoint


@pytest.mark.parametrize("body", [
    b'<!DOCTYPE r [<!ENTITY x "x">]><r/>',
    '<!DOCTYPE r [<!ENTITY x "x">]><r/>'.encode("utf-16"),
    '<?xml version="1.0" encoding="UTF-16BE"?><!DOCTYPE r><r/>'.encode("utf-16-be"),
    b'<!DOCTYPE r SYSTEM "file:///etc/passwd"><r/>',
    b"<broken", b"x" * (onvif.MAX_XML_BYTES + 1),
])
def test_unsafe_or_malformed_xml_is_rejected(body: bytes) -> None:
    with pytest.raises(onvif.OnvifError):
        onvif._parse_xml(body, "GetProfiles")


@pytest.mark.parametrize("target", ["http://192.0.2.21/onvif", "https://other.example/onvif", "http://user:secret@192.0.2.20/onvif"])
@pytest.mark.asyncio
async def test_advertised_media_cannot_forward_camera_credentials(monkeypatch, target: str) -> None:
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=capabilities(target))
    install_transport(monkeypatch, handler)
    with pytest.raises(onvif.OnvifError, match="advertised"):
        await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL, username="viewer", password="secret"))
    assert calls == [DEVICE_URL]


def test_https_service_downgrade_rejected() -> None:
    with pytest.raises(onvif.OnvifError):
        onvif._same_device_url(MEDIA_URL, DEVICE_URL.replace("http:", "https:"))


def test_equivalent_ipv6_hosts_are_supported() -> None:
    target = "http://[2001:db8:0:0::20]/media"
    assert onvif._same_device_url(target, "http://[2001:db8::20]/device") == target


@pytest.mark.asyncio
async def test_unsupported_digest_challenge_has_actionable_error(monkeypatch) -> None:
    install_transport(monkeypatch, lambda request: httpx.Response(401, headers={
        "WWW-Authenticate": 'Digest realm="camera", nonce="abcd", qop="auth-int", algorithm=MD5',
    }))
    with pytest.raises(onvif.OnvifError, match="unsupported or malformed"):
        await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL, username="viewer", password="secret"))


@pytest.mark.asyncio
async def test_camera_advertised_stream_credentials_override_onvif_credentials(monkeypatch) -> None:
    def handler(request):
        if b"GetStreamUri" not in request.content:
            return device_handler(request)
        return httpx.Response(200, content=soap(
            "<trt:GetStreamUriResponse><trt:MediaUri><tt:Uri>rtsp://stream:media-password@192.0.2.20/live</tt:Uri>"
            "</trt:MediaUri></trt:GetStreamUriResponse>"
        ))
    install_transport(monkeypatch, handler)
    payload = await onvif.camera_payload(OnvifImport(
        device_url=DEVICE_URL, name="Camera", username="onvif", password="onvif-password", profile_tokens=["main"],
    ))
    assert payload.username == "stream"
    assert payload.password == "media-password"


def test_invalid_or_external_stream_uri_rejected() -> None:
    for uri in ("file:///etc/passwd", "rtsp://192.0.2.21/live", "http://192.0.2.20/live"):
        with pytest.raises(onvif.OnvifError):
            onvif._same_device_url(uri, DEVICE_URL, stream=True)


@pytest.mark.asyncio
async def test_http_digest_challenge_supported(monkeypatch) -> None:
    authorized = []
    def handler(request):
        if not request.headers.get("authorization"):
            return httpx.Response(401, headers={"WWW-Authenticate": 'Digest realm="camera", nonce="abcd", qop="auth", algorithm=MD5'})
        authorized.append(request.headers["authorization"])
        return device_handler(request)
    install_transport(monkeypatch, handler)
    result = await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL, username="viewer", password="secret"))
    assert len(result.profiles) == 2
    assert all(value.startswith("Digest ") for value in authorized)
    assert all("secret" not in value for value in authorized)


@pytest.mark.asyncio
async def test_basic_challenge_supported_only_after_challenge(monkeypatch) -> None:
    def handler(request):
        if not request.headers.get("authorization", "").startswith("Basic "):
            return httpx.Response(401, headers={"WWW-Authenticate": 'Basic realm="camera"'})
        return device_handler(request)
    install_transport(monkeypatch, handler)
    result = await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL, username="viewer", password="secret"))
    assert len(result.profiles) == 2


@pytest.mark.parametrize("status", [301, 302, 307, 401, 403, 404, 500])
@pytest.mark.asyncio
async def test_http_failures_are_safe_and_no_redirects_followed(monkeypatch, status: int) -> None:
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "http://other.example/"}, content=b"secret diagnostic")
    install_transport(monkeypatch, handler)
    with pytest.raises(onvif.OnvifError) as error:
        await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL, password="secret"))
    assert "secret" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_timeout_is_redacted(monkeypatch) -> None:
    def handler(request):
        raise httpx.ReadTimeout("secret diagnostic", request=request)
    install_transport(monkeypatch, handler)
    with pytest.raises(onvif.OnvifError, match="timed out") as error:
        await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL))
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_fault_response_not_echoed(monkeypatch) -> None:
    install_transport(monkeypatch, lambda request: httpx.Response(500, content=soap(
        "<s:Fault><s:Reason><s:Text>NotAuthorized secret</s:Text></s:Reason></s:Fault>"
    )))
    with pytest.raises(onvif.OnvifError, match="authentication failed") as error:
        await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL))
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_nonvideo_and_duplicate_profiles_are_skipped(monkeypatch) -> None:
    def handler(request):
        if b"GetCapabilities" in request.content:
            return httpx.Response(200, content=capabilities())
        return httpx.Response(200, content=soap(
            f'<trt:GetProfilesResponse>{profile()}{profile()}<trt:Profiles token="audio"/>'
            f'{profile("unsupported", codec="RAW")}</trt:GetProfilesResponse>'
        ))
    install_transport(monkeypatch, handler)
    result = await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL))
    assert len(result.profiles) == 1
    assert len(result.warnings) == 3


@pytest.mark.asyncio
async def test_distinct_profiles_with_same_name_are_importable(monkeypatch) -> None:
    def handler(request):
        if b"GetProfiles" not in request.content:
            return device_handler(request)
        return httpx.Response(200, content=soap(
            f'<trt:GetProfilesResponse>{profile("main", "Stream")}{profile("sub", "Stream")}</trt:GetProfilesResponse>'
        ))
    install_transport(monkeypatch, handler)
    result = await onvif.camera_payload(OnvifImport(device_url=DEVICE_URL, name="Camera", profile_tokens=["main", "sub"]))
    assert [profile.name for profile in result.stream_profiles] == ["Stream", "Stream (2)"]


@pytest.mark.asyncio
async def test_profile_count_is_bounded(monkeypatch) -> None:
    def handler(request):
        if b"GetCapabilities" in request.content:
            return httpx.Response(200, content=capabilities())
        return httpx.Response(200, content=soap(
            "<trt:GetProfilesResponse>" + "".join(profile(str(i)) for i in range(33)) + "</trt:GetProfilesResponse>"
        ))
    install_transport(monkeypatch, handler)
    with pytest.raises(onvif.OnvifError, match="more than 32"):
        await onvif.inspect_profiles(OnvifConnection(device_url=DEVICE_URL))
