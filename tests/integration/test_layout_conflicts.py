from __future__ import annotations

from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mosaivue.api.app import create_app
from mosaivue.api.dependencies import login_limiter
from mosaivue.constants import SETUP_TOKEN_PATH
from mosaivue.db import Base, configure_database, get_session_factory
from mosaivue.models import DisplayProfile, Layout, LayoutRevision
from mosaivue.schemas import LayoutData, LayoutUpdate
from mosaivue.security import generate_setup_token
from mosaivue.services.backup import export_configuration, import_configuration
from mosaivue.services.layouts import LayoutService


@pytest.fixture()
def appliance(tmp_path, monkeypatch):
    login_limiter.attempts.clear()
    engine = configure_database(tmp_path / "layout-conflicts.db")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(import_module("mosaivue.api.app"), "write_capabilities", lambda: None)
    SETUP_TOKEN_PATH.unlink(missing_ok=True)
    token = generate_setup_token()
    application = create_app()
    with TestClient(application) as client:
        response = client.post("/api/v1/auth/setup", json={
            "setup_token": token, "username": "admin", "password": "Layout conflict test password!",
        })
        assert response.status_code == 201
        yield client, {"X-CSRF-Token": response.json()["csrf_token"]}, application
    Base.metadata.drop_all(engine)
    engine.dispose()
    login_limiter.attempts.clear()


def _create(client, headers, **changes):
    response = client.post("/api/v1/layouts", headers=headers, json={
        "name": "Wall", "data": {"output_width": 1920}, **changes,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _guard(wall):
    return {"expected_revision": wall["current_revision"], "expected_revision_id": wall["revision"]["id"]}


def test_guarded_api_save_returns_actionable_conflict_and_no_rejected_event(appliance):
    client, headers, application = appliance
    wall = _create(client, headers)
    events = []

    async def published(event, data):
        with get_session_factory()() as reader:
            saved = reader.get(Layout, wall["id"])
            events.append((event, saved.current_revision, saved.description))

    application.state.events.publish = published
    path = f"/api/v1/layouts/{wall['id']}"
    saved = client.put(path, headers=headers, json={"description": "New draft", **_guard(wall)})
    assert saved.status_code == 200, saved.text
    stale = client.put(path, headers=headers, json={"name": "Stale editor", **_guard(wall)})
    assert stale.status_code == 409, stale.text
    detail = stale.json()["detail"]
    assert detail["code"] == "layout_revision_conflict"
    assert detail["expected_revision"] == 1
    assert detail["current_revision"] == 2
    assert detail["current_revision_id"] == saved.json()["revision"]["id"]
    assert "Reload" in detail["message"]
    assert client.get(path).json()["name"] == "Wall"
    assert events == [("layout.changed", 2, "New draft")]


def test_legacy_save_and_history_restore_bodies_remain_optional(appliance):
    client, headers, _ = appliance
    wall = _create(client, headers)
    path = f"/api/v1/layouts/{wall['id']}"
    saved = client.put(path, headers=headers, json={"data": {"output_width": 1280}})
    assert saved.status_code == 200
    stale = client.post(f"{path}/revisions/1/restore", headers=headers, json=_guard(wall))
    assert stale.status_code == 409
    restored = client.post(f"{path}/revisions/1/restore", headers=headers, json=_guard(saved.json()))
    assert restored.status_code == 200
    assert restored.json()["current_revision"] == 3
    assert restored.json()["revision"]["data"]["output_width"] == 1920
    legacy = client.post(f"{path}/revisions/2/restore", headers=headers)
    assert legacy.status_code == 200
    assert legacy.json()["current_revision"] == 4
    assert legacy.json()["revision"]["data"]["output_width"] == 1280


@pytest.mark.parametrize("body", [
    {"expected_revision": 0}, {"expected_revision": True}, {"expected_revision": "1"},
    {"expected_revision_id": ""},
])
def test_invalid_preconditions_are_rejected_before_saving(appliance, body):
    client, headers, _ = appliance
    wall = _create(client, headers)
    response = client.put(f"/api/v1/layouts/{wall['id']}", headers=headers, json={
        "description": "Must not save", **body,
    })
    assert response.status_code == 422
    assert client.get(f"/api/v1/layouts/{wall['id']}").json()["current_revision"] == 1


@pytest.mark.parametrize("kind", ["number", "identity"])
def test_stale_activation_never_calls_renderer(appliance, kind):
    client, headers, application = appliance
    wall = _create(client, headers)

    class Renderer:
        async def call(self, method, **params):
            pytest.fail("Stale activation must not touch the renderer")

    application.state.renderer = Renderer()
    body = {"expected_revision": 2} if kind == "number" else {"expected_revision_id": "stale-id"}
    response = client.post(f"/api/v1/layouts/{wall['id']}/activate", headers=headers, json=body)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "layout_revision_conflict"
    assert not client.get(f"/api/v1/layouts/{wall['id']}").json()["active"]


@pytest.mark.parametrize("guarded", [True, False])
def test_activation_pins_revision_and_allows_concurrent_database_save(appliance, guarded):
    client, headers, application = appliance
    wall = _create(client, headers)
    calls, events = [], []

    class Renderer:
        async def call(self, method, **params):
            calls.append((method, params))
            # A real independent database writer must complete during the RPC;
            # the activation route must not hold a write lock across this await.
            with get_session_factory()() as writer:
                writer.connection().exec_driver_sql("PRAGMA busy_timeout=100")
                LayoutService(writer).update(wall["id"], LayoutUpdate(
                    description="Draft saved during apply", data=LayoutData(output_width=1280),
                    **_guard(wall),
                ))
                writer.commit()
            return {
                "state": "READY", "active_layout_id": wall["id"], "active_revision": 1,
                "active_revision_id": wall["revision"]["id"],
            }

    async def published(event, data):
        events.append((event, data))

    application.state.renderer = Renderer()
    application.state.events.publish = published
    kwargs = {"json": _guard(wall)} if guarded else {}
    response = client.post(f"/api/v1/layouts/{wall['id']}/activate", headers=headers, **kwargs)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["layout"]["active"] is True
    assert result["layout"]["current_revision"] == 2
    assert result["layout"]["description"] == "Draft saved during apply"
    assert result["renderer"]["active_revision"] == 1
    assert result["renderer"]["active_revision_id"] == wall["revision"]["id"]
    assert calls == [("apply_layout", {
        "layout_id": wall["id"], "revision": 1, "revision_id": wall["revision"]["id"],
    })]
    assert events == [("layout.activated", {
        "id": wall["id"], "revision": 1, "revision_id": wall["revision"]["id"],
    })]
    with get_session_factory()() as reader:
        assert [(row.revision, row.status) for row in reader.scalars(
            select(LayoutRevision).where(LayoutRevision.layout_id == wall["id"]).order_by(LayoutRevision.revision)
        )] == [(1, "active"), (2, "draft")]


def test_import_replacing_history_during_apply_reports_renderer_boundary(appliance, cipher):
    client, headers, application = appliance
    wall = _create(client, headers)
    events = []

    class Renderer:
        async def call(self, method, **params):
            with get_session_factory()() as writer:
                writer.connection().exec_driver_sql("PRAGMA busy_timeout=100")
                document = export_configuration(writer, cipher)
                document["layouts"][0]["revisions"][0]["data"]["output_width"] = 1280
                import_configuration(writer, cipher, document, merge=True)
                writer.commit()
            return {"state": "READY", "active_revision": 1, "active_revision_id": params["revision_id"]}

    async def published(event, data):
        events.append((event, data))

    application.state.renderer = Renderer()
    application.state.events.publish = published
    response = client.post(f"/api/v1/layouts/{wall['id']}/activate", headers=headers, json=_guard(wall))
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["renderer_applied"] is True
    assert response.json()["detail"]["current_revision_id"] != wall["revision"]["id"]
    saved = client.get(f"/api/v1/layouts/{wall['id']}").json()
    assert saved["current_revision"] == 1
    assert saved["revision"]["data"]["output_width"] == 1280
    assert saved["revision"]["status"] == "draft"
    assert not saved["active"]
    assert not events


def test_display_profile_delete_requires_explicit_detach_and_emits_after_commit(appliance):
    client, headers, application = appliance
    profile = client.post("/api/v1/display/profiles", headers=headers, json={"name": "Shared HDMI"}).json()
    wall = _create(client, headers, display_profile_id=profile["id"])
    path = f"/api/v1/display/profiles/{profile['id']}"
    response = client.delete(path, headers=headers)
    assert response.status_code == 409, response.text
    assert "Wall" in response.json()["detail"]
    assert "Detach" in response.json()["detail"]
    assert client.get(f"/api/v1/layouts/{wall['id']}").json()["display_profile_id"] == profile["id"]
    assert len(client.get("/api/v1/display/profiles").json()) == 1
    detached = client.put(f"/api/v1/layouts/{wall['id']}", headers=headers, json={
        "display_profile_id": None, **_guard(wall),
    })
    assert detached.status_code == 200
    assert detached.json()["current_revision"] == 2
    assert detached.json()["display_profile_id"] is None
    events = []

    async def published(event, data):
        with get_session_factory()() as reader:
            assert reader.get(DisplayProfile, data["id"]) is None
        events.append((event, data))

    application.state.events.publish = published
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get("/api/v1/display/profiles").json() == []
    assert events == [("display.deleted", {"id": profile["id"]})]
    assert client.delete(path, headers=headers).status_code == 404
