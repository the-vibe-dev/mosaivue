from __future__ import annotations

import time
from types import SimpleNamespace

from mosaivue.renderer.base import HealthState, Rect, StreamSpec
from mosaivue.renderer.gstreamer import GStreamerRenderer, _request_selector_pad


def test_initial_gstreamer_sources_open_one_at_a_time() -> None:
    renderer = object.__new__(GStreamerRenderer)
    opened: list[str] = []
    scheduled: list[tuple[int, object, str, object]] = []
    runtimes = {
        name: SimpleNamespace(spec=SimpleNamespace(slot_id=name, is_rotation=name == "rotation"), source=None)
        for name in ("fixed-a", "fixed-b", "rotation", "fixed-c")
    }
    renderer._slots = runtimes
    renderer._pipeline = SimpleNamespace(set_state=lambda _: "SUCCESS")
    renderer.Gst = SimpleNamespace(
        State=SimpleNamespace(PLAYING="PLAYING"),
        StateChangeReturn=SimpleNamespace(FAILURE="FAILURE"),
    )
    renderer.GLib = SimpleNamespace(
        timeout_add_seconds=lambda delay, callback, slot_id, runtime: scheduled.append(
            (delay, callback, slot_id, runtime)
        )
    )
    renderer._playing = False
    renderer._create_source_branch = lambda runtime: (
        opened.append(runtime.spec.slot_id), setattr(runtime, "source", object())
    )

    renderer._start_playback()

    assert opened == ["rotation"]
    assert [delay for delay, *_ in scheduled] == [2, 4, 6]
    assert [slot_id for _, _, slot_id, _ in scheduled] == ["fixed-a", "fixed-b", "fixed-c"]
    for _, callback, slot_id, runtime in scheduled:
        assert callback(slot_id, runtime) is False
    assert opened == ["rotation", "fixed-a", "fixed-b", "fixed-c"]


def test_delayed_source_does_not_reopen_removed_slot() -> None:
    renderer = object.__new__(GStreamerRenderer)
    runtime = SimpleNamespace(spec=SimpleNamespace(slot_id="removed"), source=None)
    renderer._slots = {}
    renderer._playing = True
    renderer._start_initial_source = lambda _: (_ for _ in ()).throw(AssertionError("reopened"))

    assert renderer._start_delayed_source("removed", runtime) is False


def test_inactive_selector_pad_accepts_live_standby_buffers() -> None:
    properties = {}
    pad = SimpleNamespace(
        find_property=lambda name: name == "always-ok",
        set_property=lambda name, value: properties.__setitem__(name, value),
    )
    selector = SimpleNamespace(request_pad_simple=lambda template: pad)

    assert _request_selector_pad(selector) is pad
    assert properties == {"always-ok": True}


def test_installed_decoder_choices_apply_to_fixed_and_rotating_tiles() -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._decoder_policy = {
        "codecs": {"h264": {"fixed": "nvh264dec", "rotation": "avdec_h264"}}
    }
    renderer._rotation_software_decode = False
    renderer.Gst = SimpleNamespace(
        ElementFactory=SimpleNamespace(find=lambda name: object() if name else None)
    )
    caps = SimpleNamespace(
        get_size=lambda: 1,
        get_structure=lambda _: SimpleNamespace(get_name=lambda: "video/x-h264"),
    )

    def factory(name: str, klass: str = "Codec/Decoder/Video") -> SimpleNamespace:
        return SimpleNamespace(get_name=lambda: name, get_metadata=lambda _: klass)

    select = renderer._select_decoder_factory
    assert select(None, None, caps, factory("nvh264dec"), False) == 0
    assert select(None, None, caps, factory("avdec_h264"), False) == 2
    assert select(None, None, caps, factory("nvh264dec"), True) == 2
    assert select(None, None, caps, factory("avdec_h264"), True) == 0
    assert select(None, None, caps, factory("h264parse", "Codec/Parser/Video"), True) == 0

    renderer._rotation_software_decode = True
    renderer._decoder_policy = {"codecs": {}}
    assert select(None, None, caps, factory("nvh264dec"), True) == 2
    assert select(None, None, caps, factory("avdec_h264"), True) == 0


def test_first_frame_timeout_retries_only_stuck_camera() -> None:
    renderer = object.__new__(GStreamerRenderer)
    now = time.monotonic()
    renderer._slots = {
        "stuck": SimpleNamespace(
            connect_started_monotonic=now - 21, restarting=False,
            source_refresh_source_id=None, reconnect_source_id=None, prepared=None,
            selector=SimpleNamespace(set_property=lambda *_: None),
            selector_placeholder_pad=object(),
            placeholder_text=SimpleNamespace(set_property=lambda *_: None),
            spec=SimpleNamespace(camera_name="Stuck"),
        ),
        "healthy": SimpleNamespace(connect_started_monotonic=now - 100),
    }
    renderer._health = {
        "stuck": SimpleNamespace(
            state=HealthState.connecting, detail=None, last_frame_monotonic=None,
            reconnect_backoff_seconds=1.0,
        ),
        "healthy": SimpleNamespace(
            state=HealthState.live, last_frame_monotonic=now,
        ),
    }
    scheduled = []
    renderer.GLib = SimpleNamespace(
        timeout_add_seconds=lambda delay, callback: scheduled.append((delay, callback)) or 1
    )

    assert renderer._watchdog_tick() is True
    assert renderer._health["stuck"].state == HealthState.offline
    assert renderer._health["stuck"].detail == "No first video frame received within 20 seconds"
    assert renderer._health["healthy"].state == HealthState.live
    assert [delay for delay, _ in scheduled] == [1]
    assert renderer._health["stuck"].reconnect_backoff_seconds == 2.0
    renderer._watchdog_tick()
    assert len(scheduled) == 1
    retried = []
    renderer._restart_stream = retried.append
    scheduled[0][1]()
    assert retried == ["stuck"]
    assert renderer._slots["stuck"].reconnect_source_id is None


def test_first_frame_timeout_waits_for_pending_branch_refresh() -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._slots = {
        "stuck": SimpleNamespace(
            connect_started_monotonic=time.monotonic() - 21,
            restarting=False, source_refresh_source_id=1,
            reconnect_source_id=None,
        )
    }
    renderer._health = {
        "stuck": SimpleNamespace(state=HealthState.reconnecting, last_frame_monotonic=None)
    }
    renderer._schedule_reconnect = lambda _: (_ for _ in ()).throw(AssertionError("duplicate retry"))

    assert renderer._watchdog_tick() is True
    assert renderer._health["stuck"].state == HealthState.reconnecting


def test_degraded_stream_without_frames_reconnects_only_that_camera() -> None:
    renderer = object.__new__(GStreamerRenderer)
    now = time.monotonic()
    renderer._slots = {
        "stuck": SimpleNamespace(
            reconnect_source_id=None, prepared=None,
            selector=SimpleNamespace(set_property=lambda *_: None),
            selector_placeholder_pad=object(),
            placeholder_text=SimpleNamespace(set_property=lambda *_: None),
            spec=SimpleNamespace(camera_name="Stuck"),
        ),
        "healthy": SimpleNamespace(),
    }
    renderer._health = {
        "stuck": SimpleNamespace(
            state=HealthState.degraded, detail="RTSP warning",
            last_frame_monotonic=now - 9, reconnect_backoff_seconds=1.0,
        ),
        "healthy": SimpleNamespace(state=HealthState.live, last_frame_monotonic=now),
    }
    scheduled = []
    renderer.GLib = SimpleNamespace(
        timeout_add_seconds=lambda delay, callback: scheduled.append((delay, callback)) or 1
    )

    assert renderer._watchdog_tick() is True
    assert renderer._health["stuck"].state == HealthState.offline
    assert renderer._health["stuck"].detail == "No video frames received for 8 seconds"
    assert renderer._health["healthy"].state == HealthState.live
    assert [delay for delay, _ in scheduled] == [1]
    renderer._restart_stream = lambda slot: scheduled.append(("restarted", slot))
    scheduled[0][1]()
    assert scheduled[-1] == ("restarted", "stuck")


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


def test_rtsps_source_uses_tcp_and_stable_jitter_buffer() -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._tls_ca_file = None
    renderer._tls_database = None
    properties = {}
    source = SimpleNamespace(
        find_property=lambda name: True,
        set_property=lambda name, value: properties.__setitem__(name, value),
    )
    spec = StreamSpec(
        slot_id="rotation", camera_id="se", camera_name="SE",
        url="rtsps://camera.example/live", rect=Rect(0, 0, 640, 360),
        latency_profile="stable", transport="udp",
    )

    renderer._configure_rtsp_source(source, spec)

    assert properties == {"latency": 800, "drop-on-latency": False, "protocols": 4}


def test_rtsps_source_uses_configured_tls_database() -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._tls_ca_file = "/etc/mosaivue/unifi-ca.crt"
    trusted_database = object()
    renderer._tls_database = trusted_database
    properties = {}
    source = SimpleNamespace(
        find_property=lambda name: name == "tls-database",
        set_property=lambda name, value: properties.__setitem__(name, value),
    )
    spec = SimpleNamespace(url="rtsps://camera.example/live", latency_profile="stable", transport="tcp")

    renderer._configure_rtsp_source(source, spec)

    assert properties == {"tls-database": trusted_database}


def test_rtsp_source_selects_video_before_opening_media_tracks() -> None:
    def caps(media: str) -> SimpleNamespace:
        return SimpleNamespace(
            get_size=lambda: 1,
            get_structure=lambda _: SimpleNamespace(get_string=lambda key: media if key == "media" else None),
        )

    assert GStreamerRenderer._select_video_rtsp_stream(None, 0, caps("video")) is True
    assert GStreamerRenderer._select_video_rtsp_stream(None, 1, caps("audio")) is False
    assert GStreamerRenderer._select_video_rtsp_stream(None, 2, None) is False


def test_unready_rotation_source_stays_responsive_then_restarts_service(monkeypatch, tmp_path) -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._started_at = time.monotonic() - 70
    selected = []
    placeholder = object()
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=SimpleNamespace(ready=False, last_frame_monotonic=None),
            failover_pending=False,
            recovery_source_id=None,
            restarting=False,
            source_refresh_source_id=None,
            reconnect_source_id=None,
            selector=SimpleNamespace(set_property=lambda key, value: selected.append((key, value))),
            selector_placeholder_pad=placeholder,
            placeholder_text=SimpleNamespace(set_property=lambda *_: None),
            spec=SimpleNamespace(camera_name="Garage Inside"),
        )
    }
    renderer._failure_callback = lambda _: None
    health = SimpleNamespace(state=HealthState.live, detail=None, last_frame_monotonic=time.monotonic() - 20)
    renderer._health = {"rotation": health}
    scheduled = []
    renderer.GLib = SimpleNamespace(timeout_add_seconds=lambda _, callback: scheduled.append(callback) or 1)
    renderer._restart_stream = lambda _: None
    exits: list[int] = []
    monkeypatch.setattr("mosaivue.renderer.gstreamer.os._exit", exits.append)
    monkeypatch.setenv("MOSAIVUE_DATA_DIR", str(tmp_path))

    assert renderer._request_failover("rotation") is True
    assert health.state == HealthState.stalled
    assert selected == [("active-pad", placeholder)]
    assert len(scheduled) == 1
    scheduled[0]()
    assert exits == [75]


def test_startup_rotation_failure_retries_its_tile_before_wall_recycle(monkeypatch, tmp_path) -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._started_at = time.monotonic() - 30
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=SimpleNamespace(ready=False, last_frame_monotonic=None),
            recovery_source_id=None, restarting=False,
            source_refresh_source_id=None, reconnect_source_id=None,
        )
    }
    renderer._health = {
        "rotation": SimpleNamespace(last_frame_monotonic=None)
    }
    scheduled = []
    retried = []
    renderer.GLib = SimpleNamespace(timeout_add_seconds=lambda _, callback: scheduled.append(callback) or 1)
    renderer._restart_stream = retried.append
    exits: list[int] = []
    monkeypatch.setattr("mosaivue.renderer.gstreamer.os._exit", exits.append)
    monkeypatch.setenv("MOSAIVUE_DATA_DIR", str(tmp_path))

    renderer._arm_rotation_recovery("rotation")
    scheduled[0]()

    assert retried == ["rotation"]
    assert exits == []
    assert len(scheduled) == 2


def test_rotation_stalled_for_two_minutes_recycles_with_healthy_fixed_tiles(
    monkeypatch, tmp_path
) -> None:
    renderer = object.__new__(GStreamerRenderer)
    now = time.monotonic()
    renderer._started_at = now - 300
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=SimpleNamespace(ready=False, last_frame_monotonic=None),
            recovery_source_id=None, restarting=False,
            source_refresh_source_id=None, reconnect_source_id=None,
            recovery_warning_monotonic=now,
        )
    }
    renderer._health = {
        "rotation": SimpleNamespace(last_frame_monotonic=now - 121),
        "fixed": SimpleNamespace(state=HealthState.live, last_frame_monotonic=now),
    }
    scheduled = []
    renderer.GLib = SimpleNamespace(
        timeout_add_seconds=lambda _, callback: scheduled.append(callback) or 1
    )
    renderer._restart_stream = lambda _: None
    exits: list[int] = []
    monkeypatch.setattr("mosaivue.renderer.gstreamer.os._exit", exits.append)
    monkeypatch.setenv("MOSAIVUE_DATA_DIR", str(tmp_path))

    renderer._arm_rotation_recovery("rotation")
    scheduled[0]()

    assert exits == [75]
    assert (tmp_path / "rotation-recovery.stamp").exists()


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
    queue = SimpleNamespace(
        set_state=lambda state: calls.append(f"queue:{state}"),
        sync_state_with_parent=lambda: calls.append("queue:resume"),
    )
    prepared = SimpleNamespace(
        source=source,
        queue=queue,
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

    assert calls == ["async", "queue:NULL", "state:NULL", "queue:resume", "resume"]
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
    prepared = SimpleNamespace(
        source=old_source, queue=object(), selector_pad=object(), frame_probe_id=1,
        spec=spec, ready=False, last_frame_monotonic=None,
    )
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
    renderer._retire_branch = lambda runtime, source, *_: runtime.retired_sources.append(source)

    renderer._schedule_prepared_refresh("rotation", prepared)
    scheduled[0]()

    assert runtime.prepared is None
    assert runtime.retired_sources == [old_source]
    assert reopened == [("rotation", spec)]


def test_prepared_failure_recycles_renderer_once_per_cooldown(monkeypatch, tmp_path) -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._health = {}
    monkeypatch.setenv("MOSAIVUE_DATA_DIR", str(tmp_path))
    exits: list[int] = []
    monkeypatch.setattr("mosaivue.renderer.gstreamer.os._exit", exits.append)

    renderer._restart_renderer_with_cooldown("rotation", "test failure")
    renderer._restart_renderer_with_cooldown("rotation", "test failure")

    assert exits == [75]
    assert (tmp_path / "rotation-recovery.stamp").exists()


def test_failed_rotation_keeps_other_live_tiles_running(monkeypatch, tmp_path) -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._health = {
        "fixed": SimpleNamespace(state=HealthState.live, last_frame_monotonic=time.monotonic()),
    }
    monkeypatch.setenv("MOSAIVUE_DATA_DIR", str(tmp_path))
    exits: list[int] = []
    monkeypatch.setattr("mosaivue.renderer.gstreamer.os._exit", exits.append)

    renderer._restart_renderer_with_cooldown("rotation", "rotation feed failed")

    assert exits == []
    assert not (tmp_path / "rotation-recovery.stamp").exists()


def test_persistent_rotation_negotiation_errors_recycle_despite_recent_frames(monkeypatch) -> None:
    renderer = object.__new__(GStreamerRenderer)
    runtime = SimpleNamespace(
        spec=SimpleNamespace(is_rotation=True),
        negotiation_failure_started_monotonic=None,
        last_negotiation_failure_monotonic=None,
        last_negotiation_recycle_attempt_monotonic=0.0,
    )
    renderer._slots = {"rotation": runtime}
    renderer._health = {
        "rotation": SimpleNamespace(
            state=HealthState.stalled, last_frame_monotonic=220.0,
        )
    }
    now = [100.0]
    monkeypatch.setattr("mosaivue.renderer.gstreamer.time.monotonic", lambda: now[0])
    recycles = []
    renderer._restart_renderer_with_cooldown = lambda *args, **kwargs: recycles.append(
        (args, kwargs)
    )

    for moment in (100.0, 150.0, 200.0):
        now[0] = moment
        renderer._observe_rotation_negotiation_failure("rotation", "reason not-negotiated (-4)")

    now[0] = 221.0
    renderer._health["rotation"].state = HealthState.live
    renderer._observe_rotation_negotiation_failure("rotation", "reason not-negotiated (-4)")
    assert recycles == []
    now[0] = 230.0
    renderer._health["rotation"].state = HealthState.stalled
    renderer._observe_rotation_negotiation_failure("rotation", "reason not-negotiated (-4)")

    assert recycles == [
        (("rotation", "persistent rotation negotiation errors"), {
            "allow_healthy_others": True, "cooldown_seconds": 1800,
        })
    ]
    now[0] = 240.0
    renderer._observe_rotation_negotiation_failure("rotation", "reason not-negotiated (-4)")
    assert len(recycles) == 1


def test_rotation_negotiation_recovery_resets_after_quiet_minute(monkeypatch) -> None:
    renderer = object.__new__(GStreamerRenderer)
    runtime = SimpleNamespace(
        spec=SimpleNamespace(is_rotation=True),
        negotiation_failure_started_monotonic=None,
        last_negotiation_failure_monotonic=None,
        last_negotiation_recycle_attempt_monotonic=0.0,
    )
    renderer._slots = {"rotation": runtime}
    renderer._health = {"rotation": SimpleNamespace(state=HealthState.stalled)}
    now = [100.0]
    monkeypatch.setattr("mosaivue.renderer.gstreamer.time.monotonic", lambda: now[0])
    recycles = []
    renderer._restart_renderer_with_cooldown = lambda *args, **kwargs: recycles.append(args)

    for moment in (100.0, 150.0, 211.0, 260.0):
        now[0] = moment
        renderer._observe_rotation_negotiation_failure("rotation", "reason not-negotiated (-4)")

    assert recycles == []
    assert runtime.negotiation_failure_started_monotonic == 211.0


def test_blocked_rotation_teardown_recycles_only_after_sustained_stall(monkeypatch, tmp_path) -> None:
    renderer = object.__new__(GStreamerRenderer)
    now = time.monotonic()
    renderer._started_at = now - 300
    prepared = SimpleNamespace(ready=False, last_frame_monotonic=None)
    runtime = SimpleNamespace(
        prepared=prepared, prepared_refresh_source_id=None,
        retired_sources=[object(), object()],
    )
    renderer._slots = {"rotation": runtime}
    renderer._health = {
        "rotation": SimpleNamespace(state=HealthState.stalled, last_frame_monotonic=now - 119),
        "fixed": SimpleNamespace(state=HealthState.live, last_frame_monotonic=now),
    }
    scheduled = []
    renderer.GLib = SimpleNamespace(
        timeout_add_seconds=lambda _, callback: scheduled.append(callback) or 1
    )
    exits: list[int] = []
    monkeypatch.setattr("mosaivue.renderer.gstreamer.os._exit", exits.append)
    monkeypatch.setenv("MOSAIVUE_DATA_DIR", str(tmp_path))

    renderer._schedule_prepared_refresh("rotation", prepared)
    scheduled.pop(0)()
    assert exits == []
    assert runtime.prepared is prepared

    renderer._health["rotation"].last_frame_monotonic = now - 121
    scheduled.pop(0)()
    assert exits == [75]
    assert (tmp_path / "rotation-recovery.stamp").exists()
    scheduled.pop(0)()
    assert exits == [75]


def test_blocked_standby_does_not_recycle_live_rotation(monkeypatch, tmp_path) -> None:
    renderer = object.__new__(GStreamerRenderer)
    renderer._started_at = time.monotonic() - 300
    prepared = SimpleNamespace(ready=False, last_frame_monotonic=None)
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=prepared, prepared_refresh_source_id=None,
            retired_sources=[object(), object()],
        )
    }
    renderer._health = {
        "rotation": SimpleNamespace(
            state=HealthState.live, last_frame_monotonic=time.monotonic() - 121,
        )
    }
    scheduled = []
    renderer.GLib = SimpleNamespace(
        timeout_add_seconds=lambda _, callback: scheduled.append(callback) or 1
    )
    exits: list[int] = []
    monkeypatch.setattr("mosaivue.renderer.gstreamer.os._exit", exits.append)
    monkeypatch.setenv("MOSAIVUE_DATA_DIR", str(tmp_path))

    renderer._schedule_prepared_refresh("rotation", prepared)
    scheduled.pop(0)()

    assert exits == []
    assert not (tmp_path / "rotation-recovery.stamp").exists()


def test_inactive_placeholder_error_is_not_treated_as_camera_failure() -> None:
    renderer = object.__new__(GStreamerRenderer)
    placeholder = SimpleNamespace(get_name=lambda: "placeholder-rotation", get_parent=lambda: None)
    renderer._slots = {"rotation": SimpleNamespace(placeholder_source=placeholder)}
    renderer.Gst = SimpleNamespace(
        MessageType=SimpleNamespace(ERROR=1, WARNING=2, EOS=3)
    )
    renderer._is_retired_message = lambda *_: False
    renderer._mark_offline = lambda *_: (_ for _ in ()).throw(AssertionError("camera marked offline"))
    message = SimpleNamespace(type=renderer.Gst.MessageType.ERROR, src=placeholder)

    renderer._on_bus_message(None, message)


def test_prepared_queue_error_does_not_fail_active_rotation() -> None:
    renderer = object.__new__(GStreamerRenderer)
    prepared_queue = SimpleNamespace(get_name=lambda: "prepared-queue-rotation", get_parent=lambda: None)
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=SimpleNamespace(source=object(), queue=prepared_queue),
            retired_sources=[], retired_queues=[], placeholder_source=object(),
            spec=SimpleNamespace(is_rotation=True),
            negotiation_failure_started_monotonic=None,
            last_negotiation_failure_monotonic=None,
            last_negotiation_recycle_attempt_monotonic=0.0,
        )
    }
    renderer.Gst = SimpleNamespace(MessageType=SimpleNamespace(ERROR=1, WARNING=2, EOS=3))
    renderer._health = {"rotation": SimpleNamespace(state=HealthState.live)}
    renderer._mark_prepared_unavailable = lambda slot: events.append(("prepared", slot))
    renderer._request_failover = lambda slot: events.append(("failover", slot))
    renderer._mark_offline = lambda slot, _: events.append(("offline", slot))
    events: list[tuple[str, str]] = []
    message = SimpleNamespace(
        type=renderer.Gst.MessageType.ERROR, src=prepared_queue,
        parse_error=lambda: (SimpleNamespace(message="stream error"), "reason not-negotiated (-4)"),
    )

    renderer._on_bus_message(None, message)

    assert events == [("prepared", "rotation")]


def test_retired_queue_errors_are_ignored() -> None:
    renderer = object.__new__(GStreamerRenderer)
    retired_queue = SimpleNamespace(get_name=lambda: "prepared-queue-rotation", get_parent=lambda: None)
    renderer._slots = {
        "rotation": SimpleNamespace(
            prepared=None, retired_sources=[], retired_queues=[retired_queue],
            placeholder_source=object(),
        )
    }
    renderer.Gst = SimpleNamespace(MessageType=SimpleNamespace(ERROR=1, WARNING=2, EOS=3))
    message = SimpleNamespace(type=renderer.Gst.MessageType.ERROR, src=retired_queue)

    renderer._on_bus_message(None, message)


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
    queue = SimpleNamespace(
        set_state=lambda state: calls.append(f"queue:{state}"),
        sync_state_with_parent=lambda: calls.append("queue:resume"),
    )
    runtime = SimpleNamespace(
        source=source,
        source_queue=queue,
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

    assert calls == ["async", "queue:NULL", "state:NULL", "queue:resume", "resume"]
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
    renderer._retire_branch = lambda runtime, source, *_: runtime.retired_sources.append(source)

    renderer._schedule_source_refresh("fixed", runtime, old_source)
    scheduled[0]()

    assert runtime.retired_sources == [old_source]
    assert runtime.source is None
    assert runtime.restarting is False
    assert created == [runtime]


def test_retired_rtsp_branch_releases_decoder_and_selector_pad_asynchronously() -> None:
    calls: list[str] = []
    pending: list[object] = []
    callbacks = []

    class Source:
        def call_async(self, callback, data) -> None:
            calls.append("scheduled")
            callbacks.append(lambda: callback(self, data))

        def set_state(self, state) -> None:
            calls.append(f"source:{state}")

    pad = SimpleNamespace(
        remove_probe=lambda _: calls.append("remove-probe"),
        unlink=lambda _: calls.append("unlink"),
    )
    queue = SimpleNamespace(
        set_state=lambda state: calls.append(f"queue:{state}"),
        get_static_pad=lambda _: pad,
    )
    selector = SimpleNamespace(release_request_pad=lambda _: calls.append("release-pad"))
    pipeline = SimpleNamespace(remove=lambda _: calls.append("remove"))
    renderer = object.__new__(GStreamerRenderer)
    renderer.Gst = SimpleNamespace(State=SimpleNamespace(NULL="NULL"))
    renderer.GLib = SimpleNamespace(idle_add=lambda callback: pending.append(callback))
    renderer._pipeline = pipeline
    runtime = SimpleNamespace(retired_sources=[], retired_queues=[], selector=selector)
    source = Source()

    renderer._retire_branch(runtime, source, queue, object(), 5)
    assert calls == ["scheduled"]
    assert runtime.retired_sources == [source]
    assert runtime.retired_queues == [queue]
    callbacks.pop()()
    assert calls == ["scheduled", "queue:NULL", "source:NULL"]
    pending.pop()()
    assert calls[-4:] == ["unlink", "release-pad", "remove", "remove"]
    assert runtime.retired_sources == []
    assert runtime.retired_queues == []
