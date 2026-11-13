from __future__ import annotations

from types import SimpleNamespace

from mosaivue.services import stream_probe


def test_probe_uses_video_caps_when_gi_video_info_has_no_get_codec(monkeypatch) -> None:
    class VideoInfo:
        def get_caps(self):
            return SimpleNamespace(
                get_size=lambda: 1,
                get_structure=lambda _: SimpleNamespace(get_name=lambda: "video/x-h264"),
            )

        def get_width(self):
            return 1024

        def get_height(self):
            return 576

        def get_framerate_num(self):
            return 30

        def get_framerate_denom(self):
            return 1

        def get_bitrate(self):
            return 0

    discoverer = SimpleNamespace(connect=lambda *args: None, discover_uri=lambda _: SimpleNamespace(get_result=lambda: 0, get_stream_list=lambda: [VideoInfo()]))
    pbutils = SimpleNamespace(Discoverer=SimpleNamespace(new=lambda _: discoverer), DiscovererVideoInfo=VideoInfo, DiscovererResult=SimpleNamespace(OK=0))
    gst = SimpleNamespace(SECOND=1)
    monkeypatch.setattr(stream_probe, "_load_gst", lambda: (gst, pbutils, None))

    result = stream_probe.probe_stream("rtsps://192.0.2.3:7441/live")
    assert result["codec"] == "video/x-h264"
    assert (result["width"], result["height"], result["framerate"]) == (1024, 576, 30)

    assert result["success"] is True
    assert result["time_to_first_frame_ms"] is None
    assert result["protocol"] == "rtsps"


def test_probe_discovery_failure_is_not_reported_as_success(monkeypatch):
    discoverer = SimpleNamespace(connect=lambda *args: None, discover_uri=lambda _: SimpleNamespace(get_result=lambda: 1))
    pbutils = SimpleNamespace(Discoverer=SimpleNamespace(new=lambda _: discoverer), DiscovererResult=SimpleNamespace(OK=0))
    monkeypatch.setattr(stream_probe, "_load_gst", lambda: (SimpleNamespace(SECOND=1), pbutils, None))
    result = stream_probe.probe_stream("rtsp://192.0.2.3/live")
    assert result["success"] is False
    assert "not successful" in result["error"]


def test_probe_without_video_is_not_reported_as_success(monkeypatch):
    discoverer = SimpleNamespace(connect=lambda *args: None, discover_uri=lambda _: SimpleNamespace(get_result=lambda: 0, get_stream_list=lambda: []))
    pbutils = SimpleNamespace(Discoverer=SimpleNamespace(new=lambda _: discoverer), DiscovererResult=SimpleNamespace(OK=0))
    monkeypatch.setattr(stream_probe, "_load_gst", lambda: (SimpleNamespace(SECOND=1), pbutils, None))
    result = stream_probe.probe_stream("rtsp://192.0.2.3/live")
    assert result["success"] is False
    assert "No usable video" in result["error"]


def test_rtsp_source_uses_requested_transport():
    settings = []
    source = SimpleNamespace(find_property=lambda name: name == "protocols", set_property=lambda *pair: settings.append(pair))
    stream_probe._configure_rtsp_transport(source, "udp")
    stream_probe._configure_rtsp_transport(source, "tcp")
    stream_probe._configure_rtsp_transport(source, "auto")
    assert settings == [("protocols", 1), ("protocols", 4)]
