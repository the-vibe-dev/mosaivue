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


def test_unready_rotation_source_does_not_stop_rtsp_in_bus_callback() -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=SimpleNamespace(ready=False, last_frame_monotonic=None),
            failover_pending=False,
        )
    }
    renderer._failure_callback = lambda _: None

    assert renderer._request_failover("rotation") is True


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
    renderer._slots = {"rotation": SimpleNamespace(prepared=prepared)}
    renderer.Gst = SimpleNamespace(State=SimpleNamespace(NULL="NULL"))
    renderer.GLib = SimpleNamespace(timeout_add_seconds=lambda _, callback: callback())

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

    renderer._prepare_stream("rotation", spec)

    assert retried == ["rotation"]


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

    renderer._restart_stream("fixed")

    assert calls == ["async", "state:NULL", "resume"]
    assert health.restart_count == 1
    assert runtime.restarting is False
