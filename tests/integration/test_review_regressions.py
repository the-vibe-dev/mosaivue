from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mosaivue.api.app import create_app
from mosaivue.api.dependencies import login_limiter
from mosaivue.config import Settings
from mosaivue.constants import SETUP_TOKEN_PATH
from mosaivue.db import Base, configure_database, get_session_factory
from mosaivue.models import Camera, Layout, User
from mosaivue.security import generate_setup_token


@pytest.fixture()
def appliance(tmp_path, monkeypatch):
    login_limiter.attempts.clear()
    engine = configure_database(tmp_path / "regressions.db")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(import_module("mosaivue.api.app"), "write_capabilities", lambda: None)
    SETUP_TOKEN_PATH.unlink(missing_ok=True)
    token = generate_setup_token()
    application = create_app()
    with TestClient(application) as client:
        setup = client.post("/api/v1/auth/setup", json={
            "setup_token": token, "username": "admin", "password": "Original secure password!",
        })
        assert setup.status_code == 201
        yield client, {"X-CSRF-Token": setup.json()["csrf_token"]}, application
    Base.metadata.drop_all(engine)
    engine.dispose()
    login_limiter.attempts.clear()


def test_password_change_revokes_other_sessions_and_keeps_current(appliance):
    client, headers, _ = appliance
    first_token = client.cookies.get("mosaivue_session")
    second = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Original secure password!"})
    assert second.status_code == 200
    second_token = client.cookies.get("mosaivue_session")
    changed = client.post("/api/v1/auth/password", headers={**headers, "Cookie": f"mosaivue_session={first_token}"}, json={
        "current_password": "Original secure password!", "new_password": "Replacement secure password!",
    })
    assert changed.status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Cookie": f"mosaivue_session={first_token}"}).status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Cookie": f"mosaivue_session={second_token}"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "Original secure password!"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "Replacement secure password!"}).status_code == 200


def test_camera_event_is_published_only_after_database_commit(appliance):
    client, headers, application = appliance
    observed = []

    async def receive(event, data):
        with get_session_factory()() as reader:
            observed.append((event, reader.get(Camera, data["id"]) is not None))

    application.state.events.publish = receive
    response = client.post("/api/v1/cameras", headers=headers, json={"name": "Committed camera", "stream_profiles": [{"url": "rtsp://192.0.2.50/live"}]})
    assert response.status_code == 201
    assert observed == [("camera.changed", True)]


def test_disabled_previews_never_start_a_stream(appliance, monkeypatch):
    client, _, _ = appliance
    monkeypatch.setattr("mosaivue.api.routes_cameras.load_settings", lambda: Settings(web_preview_enabled=False))
    def unexpected(*args, **kwargs):
        pytest.fail("Preview capture must not start when disabled")
    monkeypatch.setattr("mosaivue.api.routes_cameras.capture_thumbnail", unexpected)
    response = client.get("/api/v1/cameras/any-camera/preview")
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


@pytest.mark.parametrize("kind", ["schedule", "display", "rotation"])
def test_update_name_conflicts_return_409_and_preserve_original(appliance, kind):
    client, headers, _ = appliance
    if kind == "schedule":
        layout = client.post("/api/v1/layouts", headers=headers, json={"name": "Empty wall"}).json()
        path = "/api/v1/schedules"
        base = {"layout_id": layout["id"], "days": [0], "start_time": "08:00", "end_time": "17:00"}
    elif kind == "display":
        path, base = "/api/v1/display/profiles", {}
    else:
        camera = client.post("/api/v1/cameras", headers=headers, json={"name": "Camera", "stream_profiles": [{"url": "rtsp://192.0.2.50/live"}]}).json()
        path, base = "/api/v1/rotation-groups", {"camera_entries": [{"camera_id": camera["id"]}]}
    first = client.post(path, headers=headers, json={**base, "name": "First"})
    second = client.post(path, headers=headers, json={**base, "name": "Second"})
    assert first.status_code == second.status_code == 201
    response = client.put(f"{path}/{second.json()['id']}", headers=headers, json={**base, "name": "First"})
    assert response.status_code == 409
    assert {item["name"] for item in client.get(path).json()} == {"First", "Second"}


def test_restore_applies_only_after_committing_the_configuration(appliance):
    client, headers, application = appliance
    layout = client.post("/api/v1/layouts", headers=headers, json={"name": "Restored wall"}).json()
    exported = client.get("/api/v1/backup/export").json()
    exported["layouts"][0]["active"] = True
    seen = []

    class Renderer:
        async def call(self, method, **params):
            with get_session_factory()() as reader:
                wall = reader.get(Layout, params["layout_id"])
                seen.append((method, wall is not None, wall.active))
            return {"state": "READY"}

    application.state.renderer = Renderer()
    response = client.post("/api/v1/backup/import", headers=headers, json={"document": exported, "merge": False})
    assert response.status_code == 200, response.text
    assert response.json()["renderer_applied"] is True
    assert seen == [("apply_layout", True, True)]
    assert client.get(f"/api/v1/layouts/{layout['id']}").status_code == 404


def test_invalid_stream_url_returns_validation_error(appliance):
    client, headers, _ = appliance
    response = client.post("/api/v1/cameras", headers=headers, json={"name": "Bad URL", "stream_profiles": [{"url": "rtsp://host:invalid/live"}]})
    assert response.status_code == 422


def test_simultaneous_setup_creates_exactly_one_administrator(tmp_path, monkeypatch):
    login_limiter.attempts.clear()
    engine = configure_database(tmp_path / "setup-race.db")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(import_module("mosaivue.api.app"), "write_capabilities", lambda: None)
    SETUP_TOKEN_PATH.unlink(missing_ok=True)
    token = generate_setup_token()
    with TestClient(create_app()) as client:
        def setup(index):
            return client.post("/api/v1/auth/setup", json={"setup_token": token, "username": f"admin{index}", "password": "Original secure password!"}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(setup, (1, 2)))
        assert sorted(results) == [201, 409]
        with get_session_factory()() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 1
    Base.metadata.drop_all(engine)
    engine.dispose()
    login_limiter.attempts.clear()


@pytest.mark.parametrize("endpoint", ["import", "restore"])
def test_import_failures_do_not_echo_database_parameters(appliance, monkeypatch, endpoint):
    from sqlalchemy.exc import StatementError

    client, headers, _ = appliance
    exported = client.get("/api/v1/backup/export").json()
    archive = client.post("/api/v1/backup/create", headers=headers, json={"include_credentials": False}).content
    secret = "camera-password-must-not-escape"

    def failed_import(*args, **kwargs):
        raise StatementError("Cannot import credentials", "INSERT credential", {"password": secret}, ValueError("internal"))

    monkeypatch.setattr("mosaivue.api.routes_backup.import_configuration", failed_import)
    if endpoint == "import":
        response = client.post("/api/v1/backup/import", headers=headers, json={"document": exported})
    else:
        response = client.post("/api/v1/backup/restore", headers=headers, files={"file": ("backup.zip", archive, "application/zip")})
    assert response.status_code == 422
    assert secret not in response.text
    assert "INSERT" not in response.text
    assert "No configuration changes" in response.json()["detail"]


def test_credential_validation_does_not_echo_secret_input(appliance):
    client, headers, _ = appliance
    client.post("/api/v1/cameras", headers=headers, json={"name": "Private", "stream_profiles": [{"url": "rtsp://192.0.2.50/live"}]})
    exported = client.get("/api/v1/backup/export").json()
    secret = "secret-value-" * 200
    exported["credentials_included"] = True
    exported["cameras"][0]["credential"] = {"included": True, "username": "viewer", "password": secret}
    response = client.post("/api/v1/backup/import", headers=headers, json={"document": exported})
    assert response.status_code == 422
    assert "secret-value" not in response.text
    assert "password" in response.json()["detail"]
