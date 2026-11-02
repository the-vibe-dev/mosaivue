from types import SimpleNamespace

import pytest

from mosaivue.renderer.base import HealthState, Rect, StreamHealth, StreamSpec
from mosaivue.renderer.omxplayer import OmxPlayerRenderer, _Player


def test_omxplayer_bus_address_requires_owned_regular_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("mosaivue.renderer.omxplayer.tempfile.gettempdir", lambda: str(tmp_path))
    address = tmp_path / "omxplayerdbus.mosaivue"
    address.write_text("unix:path=/run/user/1000/bus\n", encoding="utf-8")
    address.chmod(0o640)
    assert OmxPlayerRenderer._bus_env()["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus"

    address.chmod(0o666)
    with pytest.raises(OSError):
        OmxPlayerRenderer._bus_env()

    address.unlink()
    address.symlink_to(tmp_path / "other-file")
    with pytest.raises(OSError):
        OmxPlayerRenderer._bus_env()


def _spec(url: str, aspect_mode: str) -> StreamSpec:
    return StreamSpec(
        slot_id="slot-1", camera_id="camera-1", camera_name="Camera",
        url=url, rect=Rect(x=0, y=0, width=960, height=540),
        aspect_mode=aspect_mode,
    )


def test_omxplayer_preserves_aspect_for_contain_and_uses_tls_for_rtsps() -> None:
    args = OmxPlayerRenderer._player_args(_spec("rtsps://camera.example/live", "contain"))
    assert args[args.index("--aspect-mode") + 1] == "letterbox"
    assert "--avdict" not in args


def test_omxplayer_cover_and_plain_rtsp_transport() -> None:
    args = OmxPlayerRenderer._player_args(_spec("rtsp://camera.example/live", "cover"))
    assert args[args.index("--aspect-mode") + 1] == "fill"
    assert args[args.index("--avdict") + 1] == "rtsp_transport:tcp"


def test_omxplayer_stretch_fills_window() -> None:
    args = OmxPlayerRenderer._player_args(_spec("rtsp://camera.example/live", "stretch"))
    assert args[args.index("--aspect-mode") + 1] == "stretch"


def test_warm_rotation_keeps_old_player_until_new_one_is_ready(monkeypatch) -> None:
    renderer = OmxPlayerRenderer()
    old_spec = _spec("rtsp://camera-one.example/live", "cover")
    old = _Player(
        old_spec, SimpleNamespace(poll=lambda: None),
        StreamHealth("slot-1", "camera-1", state=HealthState.live, restart_count=2, switch_count=4),
        0, "old",
    )
    renderer._players["slot-1"] = old
    stopped = []
    started = []

    def start(spec, **kwargs):
        started.append(kwargs)
        return _Player(
            spec, SimpleNamespace(poll=lambda: None),
            StreamHealth(
                spec.slot_id, spec.camera_id,
                restart_count=kwargs.get("restart_count", 0), switch_count=kwargs.get("switch_count", 0),
            ),
            0, "new",
        )

    monkeypatch.setattr(renderer, "_start", start)
    monkeypatch.setattr(renderer, "_playback_status", lambda player: True)
    commands = []
    monkeypatch.setattr(renderer, "_set_video_pos", lambda player, rect: commands.append("position") or True)
    monkeypatch.setattr(renderer, "_set_layer", lambda player, layer: commands.append("layer") or True)
    def during_handoff(seconds):
        assert seconds > 0
        assert renderer._players["slot-1"] is old
        assert not stopped
    monkeypatch.setattr("mosaivue.renderer.omxplayer.time.sleep", during_handoff)
    monkeypatch.setattr(renderer, "_stop_player", lambda player: stopped.append(player))
    replacement = _spec("rtsp://camera-two.example/live", "cover")
    replacement.camera_id = "camera-2"

    renderer.replace_stream("slot-1", replacement)

    assert started[0]["layer"] == -1
    assert commands == ["position", "layer", "layer"]
    assert stopped == [old]
    assert renderer._players["slot-1"].health.state == HealthState.live
    assert renderer._players["slot-1"].health.restart_count == 2
    assert renderer._players["slot-1"].health.switch_count == 5


def test_failed_preparation_keeps_current_camera_visible(monkeypatch) -> None:
    renderer = OmxPlayerRenderer()
    old = _Player(
        _spec("rtsp://camera-one.example/live", "cover"), SimpleNamespace(poll=lambda: None),
        StreamHealth("slot-1", "camera-1", state=HealthState.live), 0, "old",
    )
    renderer._players["slot-1"] = old
    stopped = []
    monkeypatch.setattr(renderer, "prepare_stream", lambda slot_id, spec: (_ for _ in ()).throw(RuntimeError("decoder busy")))
    monkeypatch.setattr(renderer, "_stop_player", lambda player: stopped.append(player))
    replacement = _spec("rtsp://camera-two.example/live", "cover")
    replacement.camera_id = "camera-2"

    with pytest.raises(RuntimeError, match="not ready"):
        renderer.replace_stream("slot-1", replacement)

    assert renderer._players["slot-1"] is old
    assert stopped == []


@pytest.mark.parametrize("seconds_since_confirmation,should_restart", [(2, False), (31, True)])
def test_monitor_requires_30_seconds_without_playback_confirmation(
    monkeypatch, seconds_since_confirmation: int, should_restart: bool,
) -> None:
    renderer = OmxPlayerRenderer()
    now = 1000.0
    health = StreamHealth("slot-1", "camera-1", state=HealthState.live)
    health.last_frame_monotonic = now - seconds_since_confirmation
    player = _Player(_spec("rtsp://camera.example/live", "cover"), SimpleNamespace(poll=lambda: None), health, now - 100, "player")
    renderer._players["slot-1"] = player
    waits = iter((False, True))
    renderer._stop = SimpleNamespace(wait=lambda _: next(waits))
    monkeypatch.setattr("mosaivue.renderer.omxplayer.time.monotonic", lambda: now)
    monkeypatch.setattr(renderer, "_playback_status", lambda _: False)
    stopped = []
    restarted = []
    monkeypatch.setattr(renderer, "_stop_player", stopped.append)
    monkeypatch.setattr(renderer, "_start", lambda spec, **kwargs: restarted.append(kwargs) or player)

    renderer._watch()

    assert bool(stopped) is should_restart
    assert bool(restarted) is should_restart
    if should_restart:
        assert restarted[0]["last_restart_reason"] == "Playback unconfirmed for 30 seconds"
