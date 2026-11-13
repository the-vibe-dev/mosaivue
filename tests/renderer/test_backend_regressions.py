from dataclasses import replace
from types import SimpleNamespace

import pytest

from mosaivue.renderer.base import FEATURE_NAMES, HealthState, Rect, StreamHealth, StreamSpec
from mosaivue.renderer.gstreamer import GStreamerRenderer, GStreamerUnavailable, _output_frame_rate
from mosaivue.renderer.omxplayer import OmxPlayerRenderer, _Player


class Element:
    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent

    def get_name(self):
        return self.name

    def get_parent(self):
        return self.parent


def test_gstreamer_error_attribution_does_not_confuse_slot_id_prefixes():
    renderer = object.__new__(GStreamerRenderer)
    wall = Element("wall")
    front = Element("front-1-source", wall)
    front_door = Element("front-door-2-source", wall)
    decoder = Element("front-door-2-decode", front_door)
    renderer._slots = {
        "front": SimpleNamespace(source=front),
        "front-door": SimpleNamespace(source=front_door),
    }
    assert renderer._slot_for_element(decoder) == "front-door"
    assert renderer._slot_for_element(front) == "front"
    assert renderer._slot_for_element(Element("front unrelated", wall)) is None


def test_gstreamer_attributes_prepared_and_retired_children():
    renderer = object.__new__(GStreamerRenderer)
    prepared = Element("prepared")
    retired = Element("retired")
    renderer._slots = {"tile": SimpleNamespace(
        prepared=SimpleNamespace(source=prepared, queue=Element("q")),
        retired_sources=[retired], retired_queues=[],
    )}
    assert renderer._slot_for_element(Element("decoder", prepared)) == "tile"
    assert renderer._slot_for_element(Element("rtsp", retired)) == "tile"


@pytest.mark.parametrize("value,expected", [(None, 5), ("1", 1), ("15", 15), ("60", 60)])
def test_output_fps_has_conservative_default_and_validated_override(value, expected):
    assert _output_frame_rate(value) == expected


@pytest.mark.parametrize("value", ["0", "61", "-1", "abc", "29.97", ""])
def test_output_fps_rejects_invalid_overrides(value):
    with pytest.raises(ValueError, match="MOSAIVUE_OUTPUT_FPS"):
        _output_frame_rate(value)


def test_resizing_gstreamer_output_retains_selected_compositor_fps():
    renderer = object.__new__(GStreamerRenderer)
    renderer._output_fps = 30
    caps = {}
    renderer._output_caps = SimpleNamespace(set_property=lambda key, value: caps.update({key: value}))
    renderer.Gst = SimpleNamespace(Caps=SimpleNamespace(from_string=lambda value: value))
    renderer._set_output_size(1280, 720)
    assert caps["caps"] == "video/x-raw,width=1280,height=720,framerate=30/1,pixel-aspect-ratio=1/1"


def player_spec():
    return StreamSpec("tile", "camera", "Camera", "rtsp://192.0.2.1/live", Rect(0, 0, 640, 360))


def test_omx_launch_honors_udp_opacity_and_layer():
    spec = player_spec()
    spec.transport, spec.opacity, spec.z_index = "udp", 0.5, 3
    args = OmxPlayerRenderer._player_args(spec)
    assert args[args.index("--avdict") + 1] == "rtsp_transport:udp"
    assert args[args.index("--alpha") + 1] == "128"
    assert args[args.index("--layer") + 1] == "30"


def test_omx_auto_transport_does_not_force_tcp():
    spec = player_spec()
    spec.transport = "auto"
    assert "--avdict" not in OmxPlayerRenderer._player_args(spec)


def test_omx_geometry_and_layer_changes_use_existing_player(monkeypatch):
    renderer = OmxPlayerRenderer()
    spec = player_spec()
    player = _Player(spec, object(), StreamHealth("tile", "camera"), 0, "bus")
    renderer._players["tile"] = player
    commands = []
    monkeypatch.setattr(renderer, "_set_video_pos", lambda item, rect: commands.append((item, rect)) or True)
    monkeypatch.setattr(renderer, "_set_layer", lambda item, layer: commands.append((item, layer)) or True)
    monkeypatch.setattr(renderer, "replace_stream", lambda *_: pytest.fail("Unexpected decoder restart"))
    rect = Rect(100, 50, 320, 180)
    renderer.resize_stream("tile", rect)
    renderer.set_z_order("tile", 2)
    assert player.spec.rect == rect
    assert player.spec.z_index == 2
    assert commands == [(player, rect), (player, 20)]


def test_omx_failed_geometry_command_uses_restart_fallback(monkeypatch):
    renderer = OmxPlayerRenderer()
    spec = player_spec()
    renderer._players["tile"] = _Player(spec, object(), StreamHealth("tile", "camera"), 0, "bus")
    replaced = []
    monkeypatch.setattr(renderer, "_set_video_pos", lambda *_: False)
    monkeypatch.setattr(renderer, "replace_stream", lambda slot, replacement: replaced.append(replacement))
    rect = Rect(0, 0, 320, 180)
    renderer.resize_stream("tile", rect)
    assert replaced[0].rect == rect
    assert spec.rect == Rect(0, 0, 640, 360)


@pytest.mark.parametrize("changes,ready,last_frame,expected", [
    ({}, True, 99, True),
    ({"camera_id": "other-camera"}, True, 99, False),
    ({"stream_profile_id": "other-profile"}, True, 99, False),
    ({"url": "rtsp://192.0.2.1/other"}, True, 99, False),
    ({}, False, 99, False),
    ({}, True, None, False),
    ({}, True, 90, False),
])
def test_gstreamer_standby_readiness_requires_exact_source_and_fresh_frame(
    monkeypatch, changes, ready, last_frame, expected,
):
    renderer = object.__new__(GStreamerRenderer)
    spec = player_spec()
    renderer._slots = {"tile": SimpleNamespace(prepared=SimpleNamespace(
        spec=replace(spec, **changes), ready=ready, last_frame_monotonic=last_frame,
    ))}
    monkeypatch.setattr("mosaivue.renderer.gstreamer.time.monotonic", lambda: 100)
    assert renderer._prepared_stream_ready("tile", spec) is expected
    assert renderer._prepared_stream_ready("missing-tile", spec) is False


def test_backend_feature_support_is_separate_from_hardware_availability(monkeypatch):
    def unavailable():
        raise GStreamerUnavailable("No GStreamer bindings in this environment")

    monkeypatch.setattr("mosaivue.renderer.gstreamer._import_gst", unavailable)
    monkeypatch.setattr("mosaivue.renderer.omxplayer.shutil.which", lambda _: None)
    for renderer, supported in [
        (GStreamerRenderer, {"labels", "manual_crop", "opacity", "z_order"}),
        (OmxPlayerRenderer, {"opacity", "z_order"}),
    ]:
        capabilities = renderer.detect().to_dict()
        assert capabilities["available"] is False
        assert capabilities["reason"]
        assert set(capabilities["feature_support"]) == set(FEATURE_NAMES)
        assert {key for key, value in capabilities["feature_support"].items() if value} == supported
        assert capabilities["limitations"]


def test_gstreamer_without_display_sink_explains_unavailability(monkeypatch):
    gst = SimpleNamespace(ElementFactory=SimpleNamespace(find=lambda name: None if name.endswith("sink") else object()))
    monkeypatch.setattr("mosaivue.renderer.gstreamer._import_gst", lambda: (gst, None, None))
    monkeypatch.setattr("mosaivue.renderer.gstreamer.load_decoder_policy", lambda: {"codecs": {}})
    capabilities = GStreamerRenderer.detect()
    assert capabilities.available is False
    assert capabilities.reason == "No display sink plugin is available"


def test_omx_spawn_failure_keeps_monitor_alive_and_backs_off(monkeypatch, caplog):
    renderer = OmxPlayerRenderer()
    spec = player_spec()
    failed = _Player(spec, SimpleNamespace(poll=lambda: 1), StreamHealth("tile", "camera"), 0, "failed")
    good_spec = replace(spec, slot_id="healthy", camera_id="good-camera")
    healthy = _Player(good_spec, SimpleNamespace(poll=lambda: None), StreamHealth("healthy", "good-camera"), 0, "healthy")
    renderer._players = {"tile": failed, "healthy": healthy}
    moments = iter((100, 100.5, 101, 102, 103, 107))
    clock = [0]
    attempts = []

    def wait(_):
        moment = next(moments, None)
        if moment is None:
            return True
        clock[0] = moment
        return False

    def start(*_, **kwargs):
        attempts.append(clock[0])
        raise OSError("Secret-containing command rtsp://admin:secret@camera.example/live")

    renderer._stop = SimpleNamespace(wait=wait)
    monkeypatch.setattr("mosaivue.renderer.omxplayer.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(renderer, "_playback_status", lambda _: True)
    monkeypatch.setattr(renderer, "_stop_player", lambda _: None)
    monkeypatch.setattr(renderer, "_start", start)
    renderer._watch()
    assert attempts == [100, 101, 103, 107]
    assert failed.health.restart_count == 4
    assert failed.health.reconnect_backoff_seconds == 16
    assert failed.retry_at == 115
    assert failed.health.state == HealthState.offline
    assert healthy.health.state == HealthState.live
    assert healthy.health.last_frame_monotonic == 107
    assert "admin:secret" not in caplog.text


def test_omx_successful_playback_resets_recovery_backoff(monkeypatch):
    renderer = OmxPlayerRenderer()
    spec = player_spec()
    old_health = StreamHealth("tile", "camera", restart_count=2, reconnect_backoff_seconds=32)
    failed = _Player(spec, SimpleNamespace(poll=lambda: 1), old_health, 0, "failed")
    replacement = _Player(spec, SimpleNamespace(poll=lambda: None), StreamHealth("tile", "camera"), 100, "replacement")
    renderer._players["tile"] = failed
    waits = iter((False, False, True))
    renderer._stop = SimpleNamespace(wait=lambda _: next(waits))
    monkeypatch.setattr("mosaivue.renderer.omxplayer.time.monotonic", lambda: 100)
    monkeypatch.setattr(renderer, "_stop_player", lambda _: None)
    monkeypatch.setattr(renderer, "_playback_status", lambda _: True)

    def start(spec, **kwargs):
        assert kwargs["restart_count"] == 3
        assert kwargs["last_restart_reason"] == "Player exited"
        return replacement

    monkeypatch.setattr(renderer, "_start", start)
    renderer._watch()
    assert renderer._players["tile"] is replacement
    assert replacement.health.state == HealthState.live
    assert replacement.health.reconnect_backoff_seconds == 1
    assert replacement.retry_at == 0
