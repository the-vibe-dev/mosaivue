from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.orm import Session

from mosaivue.models import Camera, Credential, Layout, LayoutRevision, RotationGroup, StreamProfile
from mosaivue.renderer.controller import RendererController
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
    controller = RendererController(backend, lambda: db, cipher)
    backend.initialize(width=1920, height=1080)
    await controller.apply_layout(layout.id, 1)
    assert backend.streams["slot-a"].rect.width == 960
    assert backend.states["slot-a"].restart_count == 0
    revision2 = LayoutRevision(layout_id=layout.id, revision=2, status="draft", data=dict(layout.revisions[0].data))
    revision2.data = {**revision2.data, "slots": [{**revision2.data["slots"][0], "width": 1.0}]}
    db.add(revision2); layout.current_revision = 2; db.commit()
    await controller.apply_layout(layout.id, 2)
    assert backend.streams["slot-a"].rect.width == 1920
    assert backend.states["slot-a"].restart_count == 0
    await controller.shutdown()
