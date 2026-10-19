#!/usr/bin/env python3
"""Exercise Rockchip KMS composition with local H.264 RTSP test streams.

Requires gir1.2-gst-rtsp-server-1.0 and the normal Mosaivue GStreamer install.
Run as the mosaivue user. Stop mosaivue-renderer.service for the default
kmssink output; --sink fakesink can run alongside the HDMI wall. No camera
credentials or database changes are used.
"""
from __future__ import annotations

import argparse
import time

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GstRtspServer  # noqa: E402

from mosaivue.renderer.base import Rect, StreamSpec  # noqa: E402
from mosaivue.renderer.gstreamer import GStreamerRenderer  # noqa: E402


def spec(index: int, *, url_index: int | None = None) -> StreamSpec:
    columns = 2
    return StreamSpec(
        slot_id=f"test-{index}",
        camera_id=f"test-{index}-{url_index if url_index is not None else index}",
        camera_name=f"Test {index}",
        url=f"rtsp://127.0.0.1:8554/demo{url_index if url_index is not None else index}",
        rect=Rect((index % columns) * 640, (index // columns) * 360, 640, 360),
        source_width=640,
        source_height=360,
        is_rotation=index == 0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--streams", type=int, choices=range(2, 5), default=4)
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--sink", choices=("kmssink", "fakesink"), default="kmssink")
    parser.add_argument("--recovery", action="store_true", help="exercise fixed and prepared source resets")
    parser.add_argument("--force-fresh", action="store_true", help="exercise prepared branch replacement")
    args = parser.parse_args()
    if args.seconds < 15:
        parser.error("--seconds must be at least 15")

    Gst.init(None)
    server = GstRtspServer.RTSPServer.new()
    server.set_service("8554")
    mounts = server.get_mount_points()
    for index in range(max(2, args.streams)):
        factory = GstRtspServer.RTSPMediaFactory.new()
        factory.set_launch(
            f"( videotestsrc is-live=true pattern={index + 1} ! "
            "video/x-raw,width=640,height=360,framerate=15/1 ! "
            "x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 bitrate=500 ! "
            "rtph264pay name=pay0 pt=96 )"
        )
        factory.set_shared(True)
        mounts.add_factory(f"/demo{index}", factory)
    server.attach(None)

    renderer = GStreamerRenderer()
    rows = (args.streams + 1) // 2
    renderer.initialize(width=1280, height=rows * 360, sink=args.sink)
    try:
        for index in range(args.streams):
            renderer.add_stream(spec(index))
        renderer.start_playback()
        renderer.prepare_stream("test-0", spec(0, url_index=1))
        time.sleep(5)
        before = renderer.health()
        if args.force_fresh:
            def force_refresh() -> None:
                prepared = renderer._slots["test-0"].prepared
                assert prepared is not None
                prepared.restarting = True
                prepared.ready = False
                prepared.last_frame_monotonic = None
                renderer._schedule_prepared_refresh("test-0", prepared)

            renderer._call(force_refresh)
            time.sleep(9)
        elif args.recovery:
            renderer._call(renderer._mark_prepared_unavailable, "test-0")
            time.sleep(6)
        renderer.activate_prepared_stream("test-0", spec(0, url_index=1))
        renderer.prepare_stream("test-0", spec(0))
        time.sleep(5)
        renderer.activate_prepared_stream("test-0", spec(0))
        if args.recovery:
            renderer.restart_stream("test-1")
            time.sleep(5)
        time.sleep(args.seconds - 10)
        after = renderer.health()
        summary = {
            "output": after["output"],
            "streams": {
                slot: {
                    "state": item["state"],
                    "frames": item["decoded_frames"],
                    "restarts": item["restart_count"],
                    "switches": item["switch_count"],
                }
                for slot, item in after["streams"].items()
            },
        }
        print(summary, flush=True)
        for slot, item in after["streams"].items():
            expected_restarts = 1 if args.recovery and slot == "test-1" else 0
            if item["state"] != "LIVE" or item["restart_count"] != expected_restarts:
                return 1
            minimum = 30 if slot == "test-0" else 60
            if item["decoded_frames"] < minimum:
                return 1
            if slot != "test-0" and item["decoded_frames"] <= before["streams"][slot]["decoded_frames"]:
                return 1
        if after["streams"]["test-0"]["switch_count"] != 2:
            return 1
        return 0
    finally:
        renderer.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
