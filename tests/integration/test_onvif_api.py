from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mosaivue.api.app import create_app
from mosaivue.api.dependencies import get_cipher
from mosaivue.models import Camera, Credential, User
from mosaivue.schemas_onvif import OnvifProfile, OnvifProfiles
from mosaivue.security import create_session, hash_password
from mosaivue.services import onvif


@pytest.fixture
def authenticated_client(db):
    user = User(username="onvif-admin", password_hash=hash_password("test fixture password"), is_admin=True)
    db.add(user)
    db.flush()
    session = create_session(db, user)
    db.commit()
    with TestClient(create_app()) as client:
        client.cookies.set("mosaivue_session", session.token)
        yield client, {"X-CSRF-Token": session.csrf_token}, user


def test_onvif_requires_auth_csrf_and_admin(authenticated_client, monkeypatch, db) -> None:
    client, headers, user = authenticated_client
    import mosaivue.api.routes_onvif as route
    async def inspect(payload):
        return OnvifProfiles(profiles=[OnvifProfile(token="main", name="Main")])
    monkeypatch.setattr(route, "inspect_profiles", inspect)
    payload = {"device_url": "http://192.0.2.20/onvif/device_service"}
    assert client.post("/api/v1/onvif/profiles", json=payload).status_code == 403
    assert client.post("/api/v1/onvif/profiles", json=payload, headers=headers).status_code == 200
    user.is_admin = False
    db.commit()
    assert client.post("/api/v1/onvif/profiles", json=payload, headers=headers).status_code == 403
    client.cookies.clear()
    assert client.post("/api/v1/onvif/profiles", json=payload).status_code == 401


def test_onvif_import_to_database_encrypts_password_and_returns_sanitized_camera(authenticated_client, db, monkeypatch) -> None:
    client, headers, _ = authenticated_client
    soap = onvif.SOAP
    def response(body):
        return httpx.Response(200, content=f'<s:Envelope xmlns:s="{soap}"><s:Body>{body}</s:Body></s:Envelope>')
    def handler(request):
        if b"GetCapabilities" in request.content:
            return response('<GetCapabilitiesResponse><Capabilities><Media><XAddr>http://192.0.2.20/media</XAddr></Media></Capabilities></GetCapabilitiesResponse>')
        if b"GetProfiles" in request.content:
            return response('<GetProfilesResponse><Profiles token="main"><Name>Main</Name><VideoEncoderConfiguration><Encoding>H264</Encoding><Resolution><Width>1280</Width><Height>720</Height></Resolution></VideoEncoderConfiguration></Profiles></GetProfilesResponse>')
        return response('<GetStreamUriResponse><MediaUri><Uri>rtsp://192.0.2.20/live</Uri></MediaUri></GetStreamUriResponse>')
    monkeypatch.setattr(onvif, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    payload = {"device_url": "http://192.0.2.20/onvif/device_service", "username": "viewer", "password": " exact secret ", "name": "ONVIF Door", "profile_tokens": ["main"]}
    imported = client.post("/api/v1/onvif/import", json=payload, headers=headers)
    assert imported.status_code == 201, imported.text
    assert imported.json()["has_password"] is True
    assert imported.json()["stream_profiles"][0]["width"] == 1280
    assert "exact secret" not in imported.text
    camera = db.scalar(select(Camera).where(Camera.name == "ONVIF Door"))
    credential = db.get(Credential, camera.credential_id)
    assert "exact secret" not in credential.encrypted_secret
    assert get_cipher().decrypt(credential.encrypted_secret, context=credential.id) == " exact secret "
    duplicate = client.post("/api/v1/onvif/import", json=payload, headers=headers)
    assert duplicate.status_code == 409
    assert len(list(db.scalars(select(Camera)))) == 1


def test_onvif_bad_network_reply_never_creates_partial_camera(authenticated_client, db, monkeypatch) -> None:
    client, headers, _ = authenticated_client
    monkeypatch.setattr(onvif, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(500, content=b"private camera diagnostic")
    )))
    imported = client.post("/api/v1/onvif/import", headers=headers, json={
        "device_url": "http://192.0.2.20/onvif/device_service", "name": "No Partial", "profile_tokens": ["main"],
    })
    assert imported.status_code == 422
    assert "private camera" not in imported.text
    assert db.scalar(select(Camera)) is None
