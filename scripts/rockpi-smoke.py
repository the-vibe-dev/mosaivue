#!/usr/bin/env python3
"""Exercise Rockchip KMS composition with local H.264 RTSP test streams.

Requires gir1.2-gst-rtsp-server-1.0 and the normal Mosaivue GStreamer install.
Run as the mosaivue user. Stop mosaivue-renderer.service for the default
kmssink output; --sink fakesink can run alongside the HDMI wall. No camera
credentials or database changes are used.
"""
from __future__ import annotations

import argparse
import os
import time

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GstRtspServer  # noqa: E402

from mosaivue.renderer.base import Rect, StreamSpec  # noqa: E402
from mosaivue.renderer.gstreamer import GStreamerRenderer  # noqa: E402


def spec(index: int, *, url_index: int | None = None) -> StreamSpec:
    columns = 2
    source_index = url_index if url_index is not None else index
    mixed = os.environ.get("MOSAIVUE_SMOKE_MIXED_RESOLUTION") == "1"
    width, height = (1024, 576) if mixed and source_index == 0 else (640, 360)
    return StreamSpec(
        slot_id=f"test-{index}",
        camera_id=f"test-{index}-{url_index if url_index is not None else index}",
        camera_name=f"Test {index}",
        url=f"rtsp://127.0.0.1:8554/demo{url_index if url_index is not None else index}",
        rect=Rect((index % columns) * 640, (index // columns) * 360, 640, 360),
        source_width=width,
        source_height=height,
        is_rotation=index == 0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--streams", type=int, choices=range(2, 5), default=4)
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--sink", choices=("kmssink", "fakesink"), default="kmssink")
    parser.add_argument("--recovery", action="store_true", help="exercise fixed and prepared source resets")
    parser.add_argument("--force-fresh", action="store_true", help="exercise prepared branch replacement")
    parser.add_argument("--with-audio", action="store_true", help="advertise an unused RTSP audio track")
    parser.add_argument("--mixed-resolution", action="store_true", help="switch 1024x576 and 640x360 feeds")
    parser.add_argument("--extra-cuts", type=int, default=0, help="additional prepared rotation cuts")
    args = parser.parse_args()
    if args.seconds < 15:
        parser.error("--seconds must be at least 15")
    if args.extra_cuts < 0:
        parser.error("--extra-cuts cannot be negative")
    if args.mixed_resolution:
        os.environ["MOSAIVUE_SMOKE_MIXED_RESOLUTION"] = "1"

    Gst.init(None)
    server = GstRtspServer.RTSPServer.new()
    server.set_service("8554")
    mounts = server.get_mount_points()
    source_count = args.streams + int(args.with_audio)
    for index in range(source_count):
        factory = GstRtspServer.RTSPMediaFactory.new()
        audio = (
            " audiotestsrc is-live=true ! audio/x-raw,rate=8000,channels=1 ! "
            "alawenc ! rtppcmapay name=pay1 pt=8"
            if args.with_audio else ""
        )
        width, height = (1024, 576) if args.mixed_resolution and index == 0 else (640, 360)
        framerate = 30 if args.mixed_resolution else 15
        factory.set_launch(
            f"( videotestsrc is-live=true pattern={index + 1} ! "
            f"video/x-raw,width={width},height={height},framerate={framerate}/1 ! "
            "x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 bitrate=500 ! "
            f"rtph264pay name=pay0 pt=96{audio} )"
        )
        factory.set_shared(True)
        mounts.add_factory(f"/demo{index}", factory)
    server.attach(None)

    renderer = GStreamerRenderer()
    rows = (args.streams + 1) // 2
    renderer.initialize(width=1280, height=rows * 360, sink=args.sink)
    try:
        for index in range(args.streams):
            # Every test mount advertises audio to exercise video-only RTSP
            # track selection in fixed and rotating branches alike.
            renderer.add_stream(spec(index, url_index=index + 1 if args.with_audio and index else None))
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
        for cut in range(args.extra_cuts):
            next_index = 1 if cut % 2 == 0 else 0
            renderer.prepare_stream("test-0", spec(0, url_index=next_index))
            time.sleep(3)
            renderer.activate_prepared_stream("test-0", spec(0, url_index=next_index))
        if args.recovery:
            renderer.restart_stream("test-1")
            time.sleep(5)
        time.sleep(args.seconds - 10)
        after = renderer.health()
        normalized = os.environ.get("MOSAIVUE_ROTATION_NORMALIZE")
        active_caps = renderer._call(
            lambda: renderer._slots["test-0"].source_queue.get_static_pad("src").get_current_caps()
        )
        prepared_caps = renderer._call(
            lambda: renderer._slots["test-0"].prepared.queue.get_static_pad("src").get_current_caps()
            if renderer._slots["test-0"].prepared else None
        )
        summary = {
            "output": after["output"],
            "streams": {
                slot: {
                    "state": item["state"],
                    "frames": item["decoded_frames"],
                    "restarts": item["restart_count"],
                    "decoder": item.get("decoder_selected"),
                    "switches": item["switch_count"],
                }
                for slot, item in after["streams"].items()
            },
            "rotation_caps": {
                "active": active_caps.to_string() if active_caps else None,
                "prepared": prepared_caps.to_string() if prepared_caps else None,
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
        if after["streams"]["test-0"]["switch_count"] != 2 + args.extra_cuts:
            return 1
        if normalized:
            width, height = map(int, normalized.split("x"))
            reported = after.get("rotation_input_caps", {}).get("test-0", {})
            if after.get("rotation_normalize_caps") is None or not reported:
                return 1
            for caps in (active_caps, prepared_caps):
                if caps is None:
                    return 1
            if reported.get("active") != active_caps.to_string() or reported.get("prepared") != prepared_caps.to_string():
                return 1
                structure = caps.get_structure(0)
                if (
                    structure.get_name() != "video/x-raw"
                    or structure.get_string("format") != "I420"
                    or structure.get_value("width") != width
                    or structure.get_value("height") != height
                    or "framerate=(fraction)15/1" not in caps.to_string()
                ):
                    return 1
        return 0
    finally:
        renderer.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
