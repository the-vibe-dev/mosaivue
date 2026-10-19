from __future__ import annotations

import time
from types import SimpleNamespace

from mosaivue.renderer.base import HealthState
from mosaivue.renderer.gstreamer import GStreamerRenderer


def test_failed_rotation_source_uses_warm_camera_without_reconnect() -> None:
    requested: list[str] = []
    renderer = object.__new__(GStreamerRenderer)
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=SimpleNamespace(ready=True, last_frame_monotonic=time.monotonic()),
            failover_pending=False,
        )
    }
    renderer._failure_callback = requested.append
    renderer.GLib = SimpleNamespace(timeout_add_seconds=lambda *_: 1)

    assert renderer._request_failover("rotation") is True
    assert renderer._request_failover("rotation") is True
    assert requested == ["rotation"]


def test_unready_rotation_source_stays_responsive_then_restarts_service(monkeypatch, tmp_path) -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=SimpleNamespace(ready=False, last_frame_monotonic=None),
            failover_pending=False,
            recovery_source_id=None,
        )
    }
    renderer._failure_callback = lambda _: None
    health = SimpleNamespace(state=HealthState.live, detail=None, last_frame_monotonic=time.monotonic() - 20)
    renderer._health = {"rotation": health}
    scheduled = []
    renderer.GLib = SimpleNamespace(timeout_add_seconds=lambda _, callback: scheduled.append(callback) or 1)
    exits: list[int] = []
    monkeypatch.setattr("mosaivue.renderer.gstreamer.os._exit", exits.append)
    monkeypatch.setenv("MOSAIVUE_DATA_DIR", str(tmp_path))

    assert renderer._request_failover("rotation") is True
    assert health.state == HealthState.stalled
    assert len(scheduled) == 1
    scheduled[0]()
    assert exits == [75]


def test_failed_prepared_source_resets_on_gstreamer_worker() -> None:
    calls: list[str] = []

    class Source:
        def call_async(self, callback, user_data) -> None:
            calls.append("async")
            callback(self, user_data)

        def set_state(self, state) -> None:
            calls.append(f"state:{state}")

        def sync_state_with_parent(self) -> None:
            calls.append("resume")

    renderer = object.__new__(GStreamerRenderer)
    source = Source()
    prepared = SimpleNamespace(
        source=source,
        ready=True,
        last_frame_monotonic=time.monotonic(),
        restarting=False,
        last_restart_monotonic=0.0,
    )
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=prepared,
            failover_pending=False,
            prepared_refresh_source_id=None,
        )
    }
    renderer.Gst = SimpleNamespace(State=SimpleNamespace(NULL="NULL"))
    renderer.GLib = SimpleNamespace(
        timeout_add_seconds=lambda delay, callback: callback() if delay == 1 else 1
    )

    renderer._mark_prepared_unavailable("rotation")

    assert calls == ["async", "state:NULL", "resume"]
    assert prepared.restarting is False
    assert prepared.ready is False


def test_next_rotation_attempt_retries_stale_prepared_source() -> None:
    renderer = object.__new__(GStreamerRenderer)
    spec = SimpleNamespace(camera_id="garage", stream_profile_id="stable", url="rtsp://camera")
    prepared = SimpleNamespace(spec=spec, ready=False, last_frame_monotonic=None)
    renderer._slots = {"rotation": SimpleNamespace(prepared=prepared)}
    retried: list[str] = []
    renderer._restart_prepared = lambda slot_id, _: retried.append(slot_id)
    renderer._schedule_prepared_refresh = lambda *_: None

    renderer._prepare_stream("rotation", spec)

    assert retried == ["rotation"]


def test_unready_prepared_branch_gets_fresh_source_without_blocking_teardown() -> None:
    renderer = object.__new__(GStreamerRenderer)
    old_source = object()
    spec = SimpleNamespace(camera_id="garage")
    prepared = SimpleNamespace(source=old_source, spec=spec, ready=False, last_frame_monotonic=None)
    runtime = SimpleNamespace(
        prepared=prepared,
        prepared_refresh_source_id=None,
        retired_sources=[],
    )
    renderer._slots = {"rotation": runtime}
    scheduled = []
    renderer.GLib = SimpleNamespace(timeout_add_seconds=lambda _, callback: scheduled.append(callback) or 1)
    reopened = []
    renderer._prepare_stream = lambda slot_id, replacement: reopened.append((slot_id, replacement))

    renderer._schedule_prepared_refresh("rotation", prepared)
    scheduled[0]()

    assert runtime.prepared is None
    assert runtime.retired_sources == [old_source]
    assert reopened == [("rotation", spec)]


def test_prepared_failure_recycles_renderer_once_per_cooldown(monkeypatch, tmp_path) -> None:
    renderer = object.__new__(GStreamerRenderer)
    monkeypatch.setenv("MOSAIVUE_DATA_DIR", str(tmp_path))
    exits: list[int] = []
    monkeypatch.setattr("mosaivue.renderer.gstreamer.os._exit", exits.append)

    renderer._restart_renderer_with_cooldown("rotation", "test failure")
    renderer._restart_renderer_with_cooldown("rotation", "test failure")

    assert exits == [75]
    assert (tmp_path / "rotation-recovery.stamp").exists()


def test_fixed_camera_restarts_source_without_blocking_video_loop() -> None:
    calls: list[str] = []

    class Source:
        def call_async(self, callback, user_data) -> None:
            calls.append("async")
            callback(self, user_data)

        def set_state(self, state) -> None:
            calls.append(f"state:{state}")

        def sync_state_with_parent(self) -> None:
            calls.append("resume")

    renderer = object.__new__(GStreamerRenderer)
    source = Source()
    runtime = SimpleNamespace(
        source=source,
        restarting=False,
        selector=SimpleNamespace(set_property=lambda *_: None),
        selector_placeholder_pad=object(),
        placeholder_text=SimpleNamespace(set_property=lambda *_: None),
        spec=SimpleNamespace(camera_name="fixed"),
    )
    renderer._slots = {"fixed": runtime}
    health = SimpleNamespace(restart_count=0, last_restart_reason=None, state=HealthState.live)
    renderer._health = {"fixed": health}
    renderer.Gst = SimpleNamespace(State=SimpleNamespace(NULL="NULL"))
    renderer.GLib = SimpleNamespace(timeout_add_seconds=lambda _, callback: callback())
    renderer._schedule_source_refresh = lambda *_: None

    renderer._restart_stream("fixed")

    assert calls == ["async", "state:NULL", "resume"]
    assert health.restart_count == 1
    assert runtime.restarting is False


def test_fixed_camera_opens_fresh_branch_if_reset_stays_stuck() -> None:
    renderer = object.__new__(GStreamerRenderer)
    old_source = object()
    runtime = SimpleNamespace(
        source=old_source,
        source_queue=object(),
        selector_camera_pad=object(),
        frame_probe_id=1,
        restarting=True,
        source_refresh_source_id=None,
        retired_sources=[],
    )
    renderer._slots = {"fixed": runtime}
    renderer._health = {
        "fixed": SimpleNamespace(state=HealthState.reconnecting, last_frame_monotonic=None)
    }
    scheduled = []
    renderer.GLib = SimpleNamespace(timeout_add_seconds=lambda _, callback: scheduled.append(callback) or 1)
    created = []
    renderer._create_source_branch = created.append

    renderer._schedule_source_refresh("fixed", runtime, old_source)
    scheduled[0]()

    assert runtime.retired_sources == [old_source]
    assert runtime.source is None
    assert runtime.restarting is False
    assert created == [runtime]
