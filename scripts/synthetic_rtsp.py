#!/usr/bin/env python3
"""Serve deterministic RTSP test patterns when GstRtspServer is installed."""
from __future__ import annotations

import argparse
import signal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8554)
    parser.add_argument("--streams", type=int, default=9)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--fps", type=int, default=15)
    args = parser.parse_args()
    try:
        import gi
        gi.require_version("Gst", "1.0")
        gi.require_version("GstRtspServer", "1.0")
        from gi.repository import GLib, Gst, GstRtspServer
    except (ImportError, ValueError) as exc:
        raise SystemExit("Install gir1.2-gst-rtsp-server-1.0 and python3-gi") from exc
    Gst.init(None)
    server = GstRtspServer.RTSPServer.new()
    server.set_service(str(args.port))
    mounts = server.get_mount_points()
    patterns = ["smpte", "ball", "snow", "zone-plate", "pinwheel", "spokes", "checkers-1", "circular", "blink"]
    for index in range(args.streams):
        factory = GstRtspServer.RTSPMediaFactory.new()
        pattern = patterns[index % len(patterns)]
        factory.set_launch(
            f"( videotestsrc is-live=true pattern={pattern} ! video/x-raw,width={args.width},height={args.height},framerate={args.fps}/1 "
            "! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 bitrate=800 ! rtph264pay name=pay0 pt=96 )"
        )
        factory.set_shared(True)
        mounts.add_factory(f"/demo{index + 1}", factory)
    server.attach(None)
    loop = GLib.MainLoop()
    signal.signal(signal.SIGINT, lambda *_: loop.quit())
    print(f"Serving {args.streams} streams at rtsp://127.0.0.1:{args.port}/demo1 ...")
    loop.run()


if __name__ == "__main__":
    main()
