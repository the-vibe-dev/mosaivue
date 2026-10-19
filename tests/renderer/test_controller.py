from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.orm import Session

from mosaivue.models import Camera, Credential, Layout, LayoutRevision, RotationGroup, StreamProfile
from mosaivue.renderer.controller import RendererController
from mosaivue.renderer.base import Rect, StreamSpec
from mosaivue.renderer.testing import TestRenderer as MemoryRenderer
from mosaivue.security import CredentialCipher


@pytest.mark.asyncio
async def test_layout_diff_resizes_without_restarting_unaffected_stream(
    db: Session, cipher: CredentialCipher
) -> None:
    credential = Credential(username="u", encrypted_secret="")
    db.add(credential); db.flush()
    credential.encrypted_secret = cipher.encrypt("p", context=credential.id)
    camera = Camera(name="Front", enabled=True, credential=credential)
    camera.stream_profiles.append(StreamProfile(name="Main", url="rtsp://192.0.2.30/live"))
    db.add(camera); db.flush()
    layout = Layout(name="Main", current_revision=1)
    db.add(layout); db.flush()
    layout.revisions.append(
        LayoutRevision(
            revision=1,
            status="active",
            data={
                "schema_version": 1,
                "background": "#000",
                "grid_columns": 12,
                "grid_rows": 12,
                "slots": [{
                    "id": "slot-a", "name": "Front", "type": "fixed", "x": 0, "y": 0,
                    "width": .5, "height": 1, "z_index": 0, "enabled": True,
                    "camera_id": camera.id, "rotation_group_id": None, "selected_camera_id": None,
                    "stream_profile_id": None, "stream_selection": "automatic", "aspect_mode": "cover",
                    "crop": {"top": 0, "right": 0, "bottom": 0, "left": 0}, "background": "#000",
                    "border": "#000", "border_width": 0, "label": None, "title_position": "none",
                    "muted": True, "locked": False, "opacity": 1, "pixel_override": None,
                }],
            },
        )
    )
    db.commit()
    backend = MemoryRenderer()
    playback_streams: list[tuple[str, ...]] = []
    backend.start_playback = lambda: playback_streams.append(tuple(backend.streams))
    controller = RendererController(backend, lambda: db, cipher)
    backend.initialize(width=1920, height=1080)
    await controller.apply_layout(layout.id, 1)
    assert playback_streams == [("slot-a",)]
    assert backend.streams["slot-a"].rect.width == 960
    assert backend.states["slot-a"].restart_count == 0
    revision2 = LayoutRevision(layout_id=layout.id, revision=2, status="draft", data=dict(layout.revisions[0].data))
    revision2.data = {**revision2.data, "slots": [{**revision2.data["slots"][0], "width": 1.0}]}
    db.add(revision2); layout.current_revision = 2; db.commit()
    await controller.apply_layout(layout.id, 2)
    assert backend.streams["slot-a"].rect.width == 1920
    assert backend.states["slot-a"].restart_count == 0
    await controller.shutdown()


@pytest.mark.asyncio
async def test_sequential_rotation_activates_prepared_source(
    db: Session, cipher: CredentialCipher
) -> None:
    first = Camera(name="First", enabled=True)
    first.stream_profiles.append(StreamProfile(name="Main", url="rtsp://192.0.2.31/live"))
    second = Camera(name="Second", enabled=True)
    second.stream_profiles.append(StreamProfile(name="Main", url="rtsp://192.0.2.32/live"))
    db.add_all((first, second))
    db.flush()
    group = RotationGroup(
        name="Pair", camera_entries=[{"camera_id": first.id}, {"camera_id": second.id}],
        preconnect="next", order_mode="sequential",
    )
    layout = Layout(name="Rotating", current_revision=1)
    db.add_all((group, layout))
    db.flush()
    db.add(LayoutRevision(
        layout_id=layout.id, revision=1, status="active",
        data={"slots": [{"id": "slot", "type": "rotation", "rotation_group_id": group.id}]},
    ))
    db.commit()

    backend = MemoryRenderer()
    backend.initialize(width=640, height=360)
    initial = StreamSpec(
        slot_id="slot", camera_id=first.id, camera_name=first.name,
        url="rtsp://192.0.2.31/live", rect=Rect(0, 0, 640, 360),
    )
    backend.add_stream(initial)
    calls: list[tuple[str, str]] = []
    backend.prepare_stream = lambda slot_id, spec: calls.append(("prepare", spec.camera_id))

    def activate(slot_id: str, spec: StreamSpec) -> None:
        calls.append(("activate", spec.camera_id))
        backend.replace_stream(slot_id, spec)

    backend.activate_prepared_stream = activate
    controller = RendererController(backend, lambda: db, cipher)
    controller.current_specs["slot"] = initial
    controller.active_layout_id = layout.id
    controller.active_revision = 1
    await controller.rotate("slot", prepare_only=True)
    controller.rotation_failures["slot"] = 2
    assert controller.status()["streams"]["slot"]["state"] == "DEGRADED"
    assert "Rotation stalled" in controller.status()["streams"]["slot"]["detail"]
    assert backend.health()["streams"]["slot"]["state"] == "LIVE"
    await controller.rotate("slot")
    assert calls == [("prepare", second.id), ("activate", second.id)]
    assert backend.streams["slot"].camera_id == second.id
    assert controller.status()["streams"]["slot"]["state"] == "LIVE"
    await controller.shutdown()
