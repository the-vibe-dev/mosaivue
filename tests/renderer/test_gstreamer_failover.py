from __future__ import annotations

import time
from types import SimpleNamespace

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
