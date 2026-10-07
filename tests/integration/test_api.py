from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from mosaivue import config
from mosaivue.api.app import create_app
from mosaivue.constants import SETUP_TOKEN_PATH
from mosaivue.db import Base, configure_database
from mosaivue.security import generate_setup_token


def test_authenticated_camera_and_layout_workflow(tmp_path: Path) -> None:
    engine = configure_database(tmp_path / "api.db")
    Base.metadata.create_all(engine)
    SETUP_TOKEN_PATH.unlink(missing_ok=True)
    token = generate_setup_token()
    with TestClient(create_app()) as client:
        setup = client.post(
            "/api/v1/auth/setup",
            json={
                "setup_token": token,
                "username": "admin",
                "password": "This is a test password 123!",
            },
        )
        assert setup.status_code == 201
        csrf = setup.json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        camera = client.post(
            "/api/v1/cameras",
            headers=headers,
            json={
                "name": "Front Door",
                "username": "viewer",
                "password": "not-returned",
                "stream_profiles": [
                    {
                        "name": "Main",
                        "url": "rtsp://viewer:not-returned@192.0.2.40/live",
                        "transport": "tcp",
                        "latency_profile": "low",
                        "priority": 0,
                    }
                ],
            },
        )
        assert camera.status_code == 201
        assert "not-returned" not in camera.text
        camera_id = camera.json()["id"]
        layout = client.post(
            "/api/v1/layouts",
            headers=headers,
            json={
                "name": "Main",
                "data": {
                    "slots": [
                        {
                            "id": "front-slot",
                            "name": "Front Door",
                            "type": "fixed",
                            "x": 0,
                            "y": 0,
                            "width": 1,
                            "height": 1,
                            "camera_id": camera_id,
                        }
                    ]
                },
            },
        )
        assert layout.status_code == 201
        assert client.get("/api/v1/cameras").status_code == 200
        assert client.get("/api/v1/layouts").status_code == 200
        assert client.get("/api/v1/system/status").status_code == 200

        # The browser loads these in parallel. Authentication must stay read-only
        # or SQLite's single-writer lock can make the dashboard hang.
        paths = ["/api/v1/cameras", "/api/v1/layouts", "/api/v1/system/status"]
        with ThreadPoolExecutor(max_workers=3) as pool:
            statuses = list(pool.map(lambda path: client.get(path).status_code, paths))
        assert statuses == [200, 200, 200]

        frontend = client.get("/")
        assert frontend.status_code == 200
        assert "style-src-attr 'unsafe-inline'" in frontend.headers["content-security-policy"]
        forbidden = client.delete(f"/api/v1/cameras/{camera_id}")
        assert forbidden.status_code == 403
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_renderer_choice_in_setup_and_dashboard_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config, "RENDERER_BACKEND_OVERRIDE_PATH", tmp_path / "renderer-backend.json")
    monkeypatch.setattr(
        "mosaivue.services.renderer_config.renderer_options",
        lambda: [
            {"name": "auto", "available": True, "reason": None},
            {"name": "omxplayer", "available": True, "reason": None},
            {"name": "gstreamer", "available": True, "reason": None},
        ],
    )
    engine = configure_database(tmp_path / "renderer-api.db")
    Base.metadata.create_all(engine)
    SETUP_TOKEN_PATH.unlink(missing_ok=True)
    token = generate_setup_token()
    with TestClient(create_app()) as client:
        status = client.get("/api/v1/auth/setup/status")
        assert status.status_code == 200
        assert {item["name"] for item in status.json()["renderer"]["options"]} == {
            "auto", "omxplayer", "gstreamer"
        }
        setup = client.post(
            "/api/v1/auth/setup",
            json={
                "setup_token": token,
                "username": "admin",
                "password": "This is a test password 123!",
                "renderer_backend": "omxplayer",
            },
        )
        assert setup.status_code == 201
        assert config.load_settings().renderer_backend == "omxplayer"
        csrf = {"X-CSRF-Token": setup.json()["csrf_token"]}
        current = client.get("/api/v1/renderer/config")
        assert current.json()["selected"] == "omxplayer"
        changed = client.put(
            "/api/v1/renderer/config", headers=csrf, json={"renderer_backend": "gstreamer"}
        )
        assert changed.status_code == 200
        assert changed.json()["selected"] == "gstreamer"
        assert config.load_settings().renderer_backend == "gstreamer"
        assert client.put(
            "/api/v1/renderer/config", json={"renderer_backend": "omxplayer"}
        ).status_code == 403
    Base.metadata.drop_all(engine)
    engine.dispose()
