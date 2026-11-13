from __future__ import annotations

from importlib import import_module

import pytest
from fastapi.testclient import TestClient

from mosaivue.api.app import create_app
from mosaivue.api.dependencies import login_limiter
from mosaivue.config import Settings
from mosaivue.constants import SETUP_TOKEN_PATH
from mosaivue.db import Base, configure_database
from mosaivue.security import generate_setup_token
from mosaivue.services.stream_work import StreamWorkBusy


@pytest.fixture()
def preview_appliance(tmp_path, monkeypatch):
    login_limiter.attempts.clear()
    engine = configure_database(tmp_path / "previews.db")
    Base.metadata.create_all(engine)
    app_module = import_module("mosaivue.api.app")
    monkeypatch.setattr(app_module, "write_capabilities", lambda: None)
    monkeypatch.setattr(app_module, "load_settings", lambda: Settings(preview_cache_ttl_seconds=30))
    SETUP_TOKEN_PATH.unlink(missing_ok=True)
    token = generate_setup_token()
    application = create_app()
    with TestClient(application) as client:
        setup = client.post("/api/v1/auth/setup", json={
            "setup_token": token, "username": "admin", "password": "Preview test password!",
        })
        assert setup.status_code == 201
        headers = {"X-CSRF-Token": setup.json()["csrf_token"]}
        camera = client.post("/api/v1/cameras", headers=headers, json={
            "name": "Preview source", "username": "viewer", "password": "original-secret",
            "stream_profiles": [
                {"name": "Main", "url": "rtsp://192.0.2.40/live", "priority": 0},
                {"name": "Sub", "url": "rtsp://192.0.2.40/sub", "priority": 1},
            ],
        })
        assert camera.status_code == 201
        yield client, headers, application, camera.json()
    Base.metadata.drop_all(engine)
    engine.dispose()
    login_limiter.attempts.clear()


def test_preview_cache_changes_with_credentials_profile_metadata_and_width(preview_appliance, monkeypatch):
    client, headers, _, camera = preview_appliance
    calls = []

    def capture(url, **kwargs):
        calls.append((url, kwargs))
        return f"jpeg-{len(calls)}".encode()

    monkeypatch.setattr("mosaivue.api.routes_cameras.capture_thumbnail", capture)
    path = f"/api/v1/cameras/{camera['id']}"
    first = client.get(path + "/preview")
    assert first.status_code == 200
    assert first.headers["content-type"] == "image/jpeg"
    assert first.headers["cache-control"] == "no-store"
    assert first.content == client.get(path + "/preview").content == b"jpeg-1"
    assert client.put(path, headers=headers, json={"password": "new-secret"}).status_code == 200
    assert client.get(path + "/preview").content == b"jpeg-2"
    assert "new-secret" in calls[-1][0] and "original-secret" not in calls[-1][0]

    profiles = camera["stream_profiles"]
    profiles[0]["transport"] = "udp"
    assert client.put(path, headers=headers, json={"stream_profiles": profiles}).status_code == 200
    assert client.get(path + "/preview").content == b"jpeg-3"
    assert calls[-1][1]["transport"] == "udp"
    profiles[0]["codec"] = "h264"
    assert client.put(path, headers=headers, json={"stream_profiles": profiles}).status_code == 200
    assert client.get(path + "/preview").content == b"jpeg-4"
    assert client.get(path + "/preview?width=800").content == b"jpeg-5"
    assert calls[-1][1]["width"] == 800
    assert client.get(path + "/preview", params={"stream_profile_id": profiles[1]["id"]}).content == b"jpeg-6"
    assert calls[-1][0].endswith("/sub")
    assert client.put(path, headers=headers, json={"clear_credentials": True}).status_code == 200
    assert client.get(path + "/preview").content == b"jpeg-7"
    assert "@" not in calls[-1][0]


def test_warm_cache_never_bypasses_session_camera_or_preview_enable_checks(preview_appliance, monkeypatch):
    client, headers, _, camera = preview_appliance
    calls = []

    def capture(*args, **kwargs):
        calls.append(True)
        return b"private-image"

    monkeypatch.setattr("mosaivue.api.routes_cameras.capture_thumbnail", capture)
    path = f"/api/v1/cameras/{camera['id']}"
    assert client.get(path + "/preview").content == b"private-image"
    assert client.put(path, headers=headers, json={"enabled": False}).status_code == 200
    assert client.get(path + "/preview").status_code != 200
    assert client.put(path, headers=headers, json={"enabled": True}).status_code == 200
    monkeypatch.setattr("mosaivue.api.routes_cameras.load_settings", lambda: Settings(web_preview_enabled=False))
    assert client.get(path + "/preview").status_code == 403
    monkeypatch.setattr("mosaivue.api.routes_cameras.load_settings", lambda: Settings(web_preview_enabled=True))
    client.cookies.clear()
    assert client.get(path + "/preview").status_code == 401
    assert calls == [True]


@pytest.mark.parametrize("operation", ["preview", "test"])
def test_saturated_camera_work_has_retryable_service_unavailable(preview_appliance, monkeypatch, operation):
    client, headers, application, camera = preview_appliance

    async def busy(*args, **kwargs):
        raise StreamWorkBusy()

    monkeypatch.setattr(application.state.stream_work, "run", busy)
    method = client.get if operation == "preview" else client.post
    response = method(f"/api/v1/cameras/{camera['id']}/{operation}", headers=headers)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "2"
    assert "busy" in response.json()["detail"]


def test_probe_results_are_fresh_and_retain_existing_response_shape(preview_appliance, monkeypatch):
    client, headers, _, camera = preview_appliance
    calls = []

    def probe(*args, **kwargs):
        calls.append(True)
        return {"success": True, "response_time_ms": len(calls), "time_to_first_frame_ms": None}

    monkeypatch.setattr("mosaivue.api.routes_cameras.probe_stream", probe)
    path = f"/api/v1/cameras/{camera['id']}/test"
    assert client.post(path).status_code == 403
    first = client.post(path, headers=headers)
    second = client.post(path, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["profile_id"] == camera["stream_profiles"][0]["id"]
    assert first.json()["response_time_ms"] == 1
    assert second.json()["response_time_ms"] == 2
    assert second.json()["time_to_first_frame_ms"] is None
