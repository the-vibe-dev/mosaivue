from types import SimpleNamespace

import pytest

from mosaivue.renderer.base import Rect, StreamHealth, StreamSpec
from mosaivue.renderer.gstreamer import GStreamerRenderer, _output_frame_rate
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
