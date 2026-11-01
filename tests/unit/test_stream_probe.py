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

    discoverer = SimpleNamespace(discover_uri=lambda _: SimpleNamespace(get_stream_list=lambda: [VideoInfo()]))
    pbutils = SimpleNamespace(Discoverer=SimpleNamespace(new=lambda _: discoverer), DiscovererVideoInfo=VideoInfo)
    gst = SimpleNamespace(SECOND=1)
    monkeypatch.setattr(stream_probe, "_load_gst", lambda: (gst, pbutils, None))

    result = stream_probe.probe_stream("rtsps://192.0.2.3:7441/live")
    assert result["codec"] == "video/x-h264"
    assert (result["width"], result["height"], result["framerate"]) == (1024, 576, 30)
