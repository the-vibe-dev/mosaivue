from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mosaivue.models import Camera, Layout, LayoutRevision, RotationGroup, StreamProfile
from mosaivue.renderer.base import Rect, StreamSpec
from mosaivue.renderer.controller import RendererController
from mosaivue.renderer.testing import TestRenderer as MemoryRenderer
from mosaivue.security import CredentialCipher


def seed_wall(db: Session, *, slots: int = 1) -> dict:
    cameras = []
    for number in range(3):
        camera = Camera(name=f"Camera {number}", enabled=True)
        camera.stream_profiles.extend([
            StreamProfile(name="Main", url=f"rtsp://192.0.2.{number + 10}/main", width=1920, height=1080, priority=0),
            StreamProfile(name="Sub", url=f"rtsp://192.0.2.{number + 10}/sub", width=640, height=360, priority=1),
        ])
        db.add(camera)
        cameras.append(camera)
    db.flush()
    group = RotationGroup(
        name="Rotation", interval_seconds=600, enabled=True,
        camera_entries=[{"camera_id": camera.id} for camera in cameras],
    )
    layout = Layout(name="Wall", current_revision=1)
    db.add_all([group, layout])
    db.flush()
    db.add(LayoutRevision(layout_id=layout.id, revision=1, status="active", data={
        "output_width": 1920, "output_height": 1080,
        "slots": [
            {"id": f"slot-{index}", "type": "rotation", "rotation_group_id": group.id,
             "x": index / 4, "y": 0, "width": 0.25, "height": 0.25,
             "stream_selection": "automatic"}
            for index in range(slots)
        ],
    }))
    result = {
        "layout": layout.id, "group": group.id,
        "cameras": [camera.id for camera in cameras],
        "substreams": [camera.stream_profiles[1].id for camera in cameras],
    }
    db.commit()
    return result


async def controller_for(db: Session, cipher: CredentialCipher, data: dict) -> RendererController:
    backend = MemoryRenderer()
    backend.initialize(width=1920, height=1080)
    controller = RendererController(backend, lambda: db, cipher)
    # Keep timers dormant while exercising explicit commands.
    controller.pause_rotation(data["group"])
    await controller.apply_layout(data["layout"])
    return controller


@pytest.mark.asyncio
async def test_shared_rotation_group_has_independent_tile_positions(db, cipher):
    data = seed_wall(db, slots=2)
    controller = await controller_for(db, cipher, data)
    try:
        await controller.rotate("slot-0")
        await controller.rotate("slot-1")
        assert controller.current_specs["slot-0"].camera_id == data["cameras"][1]
        assert controller.current_specs["slot-1"].camera_id == data["cameras"][1]
        assert controller.rotation_cursors["slot-0"].index == 1
        assert controller.rotation_cursors["slot-1"].index == 1
    finally:
        await controller.shutdown()


@pytest.mark.asyncio
async def test_automatic_substream_selection_survives_rotation(db, cipher):
    data = seed_wall(db)
    controller = await controller_for(db, cipher, data)
    try:
        assert controller.current_specs["slot-0"].stream_profile_id == data["substreams"][0]
        await controller.rotate("slot-0", prepare_only=True)
        await controller.rotate("slot-0")
        assert controller.current_specs["slot-0"].stream_profile_id == data["substreams"][1]
        assert controller.current_specs["slot-0"].url.endswith("/sub")
    finally:
        await controller.shutdown()


@pytest.mark.asyncio
async def test_disabled_camera_is_skipped_and_disabled_group_stops_advancing(db, cipher):
    data = seed_wall(db)
    controller = await controller_for(db, cipher, data)
    try:
        db.get(Camera, data["cameras"][1]).enabled = False
        db.commit()
        await controller.rotate("slot-0")
        assert controller.current_specs["slot-0"].camera_id == data["cameras"][2]
        db.get(RotationGroup, data["group"]).enabled = False
        db.commit()
        await controller.rotate("slot-0")
        assert controller.current_specs["slot-0"].camera_id == data["cameras"][2]
    finally:
        await controller.shutdown()


@pytest.mark.parametrize("behavior,expected_index", [("skip", 1), ("hold", 0)])
@pytest.mark.asyncio
async def test_failed_rotation_honors_skip_or_hold(db, cipher, behavior, expected_index):
    data = seed_wall(db)
    db.get(RotationGroup, data["group"]).failure_behavior = behavior
    db.commit()
    controller = await controller_for(db, cipher, data)
    original = controller.backend.activate_prepared_stream

    def reject_second(slot_id, spec):
        if spec.camera_id == data["cameras"][1]:
            raise RuntimeError("Second camera unavailable")
        original(slot_id, spec)

    controller.backend.activate_prepared_stream = reject_second
    try:
        with pytest.raises(RuntimeError, match="Second camera"):
            await controller.rotate("slot-0")
        assert controller.current_specs["slot-0"].camera_id == data["cameras"][0]
        assert controller.rotation_cursors["slot-0"].index == expected_index
        if behavior == "skip":
            await controller.rotate("slot-0")
            assert controller.current_specs["slot-0"].camera_id == data["cameras"][2]
        else:
            with pytest.raises(RuntimeError, match="Second camera"):
                await controller.rotate("slot-0")
    finally:
        await controller.shutdown()


@pytest.mark.asyncio
async def test_invalid_focus_preserves_running_rotation(db, cipher):
    data = seed_wall(db)
    controller = await controller_for(db, cipher, data)
    task = controller.rotation_tasks["slot-0"]
    try:
        with pytest.raises(KeyError):
            await controller.focus_camera("does-not-exist")
        assert controller.rotation_tasks["slot-0"] is task
        assert not task.cancelled()
        assert not controller.focused
        assert "slot-0" in controller.backend.streams
    finally:
        await controller.shutdown()


@pytest.mark.asyncio
async def test_focus_before_first_layout_starts_output(db, cipher):
    data = seed_wall(db)
    backend = MemoryRenderer()
    backend.initialize(width=1920, height=1080)
    starts = []
    backend.start_playback = lambda: starts.append(tuple(backend.streams))
    controller = RendererController(backend, lambda: db, cipher)
    try:
        await controller.focus_camera(data["cameras"][0])
        assert starts == [("__focus__",)]
        assert controller.focused
        assert controller.current_specs["__focus__"].source_width == 1920
    finally:
        await controller.shutdown()


@pytest.mark.asyncio
async def test_partial_layout_failure_restores_specs_dimensions_and_rotation(db, cipher):
    data = seed_wall(db)
    controller = await controller_for(db, cipher, data)
    layout = db.get(Layout, data["layout"])
    layout.current_revision = 2
    db.add(LayoutRevision(layout_id=data["layout"], revision=2, data={
        "output_width": 1280, "output_height": 720,
        "slots": [{"id": "new-slot", "type": "fixed", "camera_id": data["cameras"][1],
                   "x": 0, "y": 0, "width": 1, "height": 1}],
    }))
    db.commit()
    original = controller.backend.add_stream

    def partial_add(spec):
        original(spec)
        if spec.slot_id == "new-slot":
            raise RuntimeError("Decoder rejected new branch after creation")

    controller.backend.add_stream = partial_add
    old_task = controller.rotation_tasks["slot-0"]
    try:
        with pytest.raises(RuntimeError, match="Decoder rejected"):
            await controller.apply_layout(data["layout"])
        assert controller.active_revision == 1
        assert set(controller.backend.streams) == {"slot-0"}
        assert controller.backend.streams["slot-0"].camera_id == data["cameras"][0]
        assert controller.backend.streams["slot-0"].rect == Rect(0, 0, 480, 270)
        assert (controller.backend.width, controller.backend.height) == (1920, 1080)
        assert (controller.output_width, controller.output_height) == (1920, 1080)
        assert controller.rotation_tasks["slot-0"] is old_task
    finally:
        await controller.shutdown()


def test_changing_transport_and_latency_replaces_source():
    backend = MemoryRenderer()
    controller = RendererController(backend, None, None)
    before = StreamSpec("slot", "camera", "Camera", "rtsp://192.0.2.1/live", Rect(0, 0, 640, 360))
    controller._apply_diff({"slot": before})
    replacements = []
    original = backend.replace_stream

    def record(slot_id, spec):
        replacements.append((spec.transport, spec.latency_profile))
        original(slot_id, spec)

    backend.replace_stream = record
    after = StreamSpec("slot", "camera", "Camera", "rtsp://192.0.2.1/live", Rect(0, 0, 640, 360), transport="udp", latency_profile="stable")
    controller._apply_diff({"slot": after})
    assert replacements == [("udp", "stable")]


@pytest.mark.asyncio
async def test_shutdown_joins_rotation_and_focus_tasks(db, cipher):
    data = seed_wall(db)
    controller = await controller_for(db, cipher, data)
    task = controller.rotation_tasks["slot-0"]
    focus_task = asyncio.create_task(asyncio.sleep(600))
    controller.focus_restore_task = focus_task
    await controller.shutdown()
    assert task.done()
    assert focus_task.done()


@pytest.mark.asyncio
async def test_manual_previous_prepares_requested_camera_before_cutover(db, cipher, monkeypatch):
    data = seed_wall(db)
    controller = await controller_for(db, cipher, data)
    prepared = []
    readiness = iter((False, True))
    original_switch = controller.backend.activate_prepared_stream

    def prepare(slot_id, spec):
        assert controller.current_specs[slot_id].camera_id == data["cameras"][0]
        prepared.append(spec.camera_id)

    def ready(slot_id, spec):
        assert prepared[-1] == spec.camera_id
        assert controller.current_specs[slot_id].camera_id == data["cameras"][0]
        return next(readiness)

    def switch(slot_id, spec):
        assert prepared[-1] == data["cameras"][2]
        original_switch(slot_id, spec)

    monkeypatch.setattr(controller.backend, "prepare_stream", prepare)
    monkeypatch.setattr(controller.backend, "prepared_stream_ready", ready)
    monkeypatch.setattr(controller.backend, "activate_prepared_stream", switch)
    try:
        await controller.rotate("slot-0", prepare_only=True)
        await controller.rotate("slot-0", direction=-1, manual=True)
        assert prepared == [data["cameras"][1], data["cameras"][2]]
        assert controller.current_specs["slot-0"].camera_id == data["cameras"][2]
        assert controller.rotation_cursors["slot-0"].index == 2
    finally:
        await controller.shutdown()


@pytest.mark.parametrize("failure_behavior", ["skip", "hold"])
@pytest.mark.asyncio
async def test_manual_rotation_timeout_keeps_current_camera_and_cursor(
    db, cipher, monkeypatch, failure_behavior,
):
    data = seed_wall(db)
    db.get(RotationGroup, data["group"]).failure_behavior = failure_behavior
    db.commit()
    controller = await controller_for(db, cipher, data)
    cancelled = []
    monkeypatch.setattr("mosaivue.renderer.controller.MANUAL_ROTATION_READY_TIMEOUT", 0)
    monkeypatch.setattr(controller.backend, "prepared_stream_ready", lambda *_: False)
    monkeypatch.setattr(controller.backend, "cancel_prepared", cancelled.append)
    monkeypatch.setattr(controller.backend, "activate_prepared_stream", lambda *_: pytest.fail("Premature cutover"))
    try:
        with pytest.raises(RuntimeError, match="current camera was kept"):
            await controller.rotate("slot-0", manual=True)
        assert controller.current_specs["slot-0"].camera_id == data["cameras"][0]
        assert controller.backend.streams["slot-0"].camera_id == data["cameras"][0]
        assert controller.rotation_cursors["slot-0"].index == 0
        assert cancelled == ["slot-0"]
    finally:
        await controller.shutdown()


@pytest.mark.asyncio
async def test_manual_rotation_respects_disabled_preconnection(db, cipher, monkeypatch):
    data = seed_wall(db)
    db.get(RotationGroup, data["group"]).preconnect = "off"
    db.commit()
    controller = await controller_for(db, cipher, data)
    monkeypatch.setattr(controller.backend, "prepare_stream", lambda *_: pytest.fail("Unexpected preparation"))
    monkeypatch.setattr(controller.backend, "activate_prepared_stream", lambda *_: pytest.fail("Unexpected standby activation"))
    try:
        await controller.rotate("slot-0", manual=True)
        assert controller.current_specs["slot-0"].camera_id == data["cameras"][1]
    finally:
        await controller.shutdown()


@pytest.mark.asyncio
async def test_status_caches_capabilities_and_preserves_wall_identity_during_focus(db, cipher, monkeypatch):
    data = seed_wall(db)
    controller = await controller_for(db, cipher, data)
    monkeypatch.setattr(controller.backend, "capabilities", lambda: pytest.fail("Repeated hardware detection"))
    try:
        status = controller.status()
        assert status["capabilities"]["feature_support"]["labels"] is True
        status["capabilities"]["feature_support"]["labels"] = False
        status["capabilities"]["limitations"].clear()
        await controller.focus_camera(data["cameras"][1])
        focused = controller.status()
        assert focused["focused"] is True
        assert focused["active_layout_id"] == data["layout"]
        assert focused["active_revision"] == 1
        assert focused["active_revision_id"] == status["active_revision_id"]
        assert focused["capabilities"]["feature_support"]["labels"] is True
        assert focused["capabilities"]["limitations"]
    finally:
        await controller.shutdown()


@pytest.mark.asyncio
async def test_apply_revision_identity_guard_rejects_before_backend_mutation(db, cipher, monkeypatch):
    data = seed_wall(db)
    controller = await controller_for(db, cipher, data)
    old_id = controller.active_revision_id
    old_task = controller.rotation_tasks["slot-0"]
    monkeypatch.setattr(controller, "_apply_transaction", lambda *_: pytest.fail("Mutated wall for stale revision"))
    try:
        with pytest.raises(ValueError, match="identity changed"):
            await controller.apply_layout(data["layout"], 1, revision_id="superseded-revision")
        assert controller.active_revision_id == old_id
        assert controller.rotation_tasks["slot-0"] is old_task
        assert controller.current_specs["slot-0"].camera_id == data["cameras"][0]
    finally:
        await controller.shutdown()


@pytest.mark.asyncio
async def test_same_number_import_requires_reapply_before_rotation_or_focus_restore(db, cipher):
    data = seed_wall(db)
    controller = await controller_for(db, cipher, data)
    old_id = controller.active_revision_id
    row = db.scalar(select(LayoutRevision).where(LayoutRevision.layout_id == data["layout"]))
    row.id = "replacement-revision-identity"
    db.commit()
    try:
        with pytest.raises(ValueError, match="revision was replaced"):
            await controller.rotate("slot-0", manual=True)
        assert controller.current_specs["slot-0"].camera_id == data["cameras"][0]
        await controller.focus_camera(data["cameras"][1])
        assert controller.status()["active_revision_id"] == old_id
        with pytest.raises(ValueError, match="identity changed"):
            await controller.restore_layout()
        assert controller.focused
        assert controller.current_specs["__focus__"].camera_id == data["cameras"][1]
        status = await controller.apply_layout(data["layout"], 1, revision_id="replacement-revision-identity")
        assert status["active_revision_id"] == "replacement-revision-identity"
        assert not controller.focused
    finally:
        await controller.shutdown()
