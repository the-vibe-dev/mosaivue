from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

LOGGER = logging.getLogger(__name__)


class StreamProbeUnavailable(RuntimeError):
    pass


def _load_gst() -> tuple[Any, Any, Any]:
    try:
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstPbutils", "1.0")
        from gi.repository import GLib, Gst, GstPbutils

        Gst.init(None)
        return Gst, GstPbutils, GLib
    except (ImportError, ValueError) as exc:
        raise StreamProbeUnavailable(
            "GStreamer Python bindings and gst-plugins-base are required for stream probing"
        ) from exc


def probe_stream(url: str, timeout_seconds: int = 10) -> dict[str, Any]:
    Gst, GstPbutils, _ = _load_gst()
    started = time.monotonic()
    discoverer = GstPbutils.Discoverer.new(timeout_seconds * Gst.SECOND)
    try:
        info = discoverer.discover_uri(url)
    except Exception as exc:
        raise RuntimeError(f"Stream discovery failed: {exc}") from exc
    duration = (time.monotonic() - started) * 1000
    result: dict[str, Any] = {
        "success": True,
        "response_time_ms": round(duration, 1),
        "time_to_first_frame_ms": round(duration, 1),
        "transport": urlsplit(url).scheme.lower(),
        "codec": None,
        "width": None,
        "height": None,
        "framerate": None,
        "bitrate": None,
        "decoder_selected": None,
    }
    streams = info.get_stream_list() or []
    for stream in streams:
        if isinstance(stream, GstPbutils.DiscovererVideoInfo):
            caps = stream.get_caps()
            structure = caps.get_structure(0) if caps and caps.get_size() else None
            result.update(
                {
                    "codec": stream.get_codec() or (structure.get_name() if structure else None),
                    "width": stream.get_width(),
                    "height": stream.get_height(),
                    "framerate": (
                        stream.get_framerate_num() / stream.get_framerate_denom()
                        if stream.get_framerate_denom()
                        else None
                    ),
                    "bitrate": stream.get_bitrate() or None,
                }
            )
            break
    return result


def capture_thumbnail(url: str, *, width: int = 640, timeout_seconds: int = 10) -> bytes:
    try:
        return _capture_thumbnail_gstreamer(url, width=width, timeout_seconds=timeout_seconds)
    except Exception as exc:
        LOGGER.warning("GStreamer thumbnail capture failed (%s); trying FFmpeg", type(exc).__name__)
        return _capture_thumbnail_ffmpeg(url, width=width, timeout_seconds=timeout_seconds)


def _capture_thumbnail_ffmpeg(url: str, *, width: int, timeout_seconds: int) -> bytes:
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error"]
    if urlsplit(url).scheme.lower() == "rtsp":
        command.extend(["-rtsp_transport", "tcp"])
    command.extend([
        "-i", url, "-an", "-frames:v", "1", "-vf", f"scale={width}:-2",
        "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
    ])
    try:
        result = subprocess.run(command, capture_output=True, timeout=max(timeout_seconds, 15), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("FFmpeg thumbnail capture failed") from exc
    if result.returncode != 0 or not result.stdout.startswith(b"\xff\xd8\xff"):
        raise RuntimeError("FFmpeg thumbnail capture failed")
    return result.stdout


def _capture_thumbnail_gstreamer(url: str, *, width: int, timeout_seconds: int) -> bytes:
    Gst, _, GLib = _load_gst()
    pipeline = Gst.Pipeline.new("thumbnail")
    source = Gst.ElementFactory.make("uridecodebin", "source")
    convert = Gst.ElementFactory.make("videoconvert", "convert")
    scale = Gst.ElementFactory.make("videoscale", "scale")
    capsfilter = Gst.ElementFactory.make("capsfilter", "caps")
    encoder = Gst.ElementFactory.make("jpegenc", "encoder")
    sink = Gst.ElementFactory.make("appsink", "sink")
    if not all((source, convert, scale, capsfilter, encoder, sink)):
        raise StreamProbeUnavailable("Required GStreamer thumbnail elements are unavailable")
    source.set_property("uri", url)
    capsfilter.set_property("caps", Gst.Caps.from_string(f"video/x-raw,width={width}"))
    sink.set_property("emit-signals", True)
    sink.set_property("sync", False)
    sink.set_property("max-buffers", 1)
    sink.set_property("drop", True)
    for element in (source, convert, scale, capsfilter, encoder, sink):
        pipeline.add(element)
    if not convert.link(scale) or not scale.link(capsfilter) or not capsfilter.link(encoder) or not encoder.link(sink):
        raise RuntimeError("Unable to link thumbnail pipeline")

    def on_pad_added(_: Any, pad: Any) -> None:
        sink_pad = convert.get_static_pad("sink")
        caps = pad.get_current_caps() or pad.query_caps(None)
        if caps and caps.to_string().startswith("video/") and not sink_pad.is_linked():
            pad.link(sink_pad)

    source.connect("pad-added", on_pad_added)
    pipeline.set_state(Gst.State.PLAYING)
    try:
        sample = sink.emit("try-pull-sample", timeout_seconds * Gst.SECOND)
        if sample is None:
            bus = pipeline.get_bus()
            message = bus.timed_pop_filtered(
                0, Gst.MessageType.ERROR | Gst.MessageType.EOS
            )
            if message and message.type == Gst.MessageType.ERROR:
                error, debug = message.parse_error()
                raise RuntimeError(f"Thumbnail capture failed: {error}; {debug or ''}")
            raise TimeoutError("Timed out waiting for a video frame")
        buffer = sample.get_buffer()
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            raise RuntimeError("Unable to read thumbnail buffer")
        try:
            return bytes(map_info.data)
        finally:
            buffer.unmap(map_info)
    finally:
        pipeline.set_state(Gst.State.NULL)
