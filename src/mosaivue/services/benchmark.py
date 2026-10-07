from __future__ import annotations

import time
from typing import Any

import psutil

from .capabilities import detect_capabilities


class BenchmarkUnavailable(RuntimeError):
    pass


def synthetic_benchmark(
    *, streams: int = 6, width: int = 1920, height: int = 1080, duration_seconds: int = 5
) -> dict[str, Any]:
    if streams < 1 or streams > 16:
        raise ValueError("Stream count must be between 1 and 16")
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
    except (ImportError, ValueError) as exc:
        raise BenchmarkUnavailable("GStreamer Python bindings are unavailable") from exc

    pipeline = Gst.Pipeline.new("mosaivue-benchmark")
    compositor = Gst.ElementFactory.make("compositor", "mix")
    sink = Gst.ElementFactory.make("fakesink", "sink")
    if not compositor or not sink:
        raise BenchmarkUnavailable("GStreamer compositor/fakesink elements are unavailable")
    sink.set_property("sync", False)
    pipeline.add(compositor)
    pipeline.add(sink)
    compositor.link(sink)
    columns = max(1, int(streams**0.5))
    rows = (streams + columns - 1) // columns
    tile_width = width // columns
    tile_height = height // rows
    counters = [0 for _ in range(streams)]
    probes: list[tuple[Any, int]] = []
    for index in range(streams):
        source = Gst.ElementFactory.make("videotestsrc", f"source-{index}")
        capsfilter = Gst.ElementFactory.make("capsfilter", f"caps-{index}")
        convert = Gst.ElementFactory.make("videoconvert", f"convert-{index}")
        scale = Gst.ElementFactory.make("videoscale", f"scale-{index}")
        if not all((source, capsfilter, convert, scale)):
            raise BenchmarkUnavailable("Required synthetic source elements are unavailable")
        source.set_property("is-live", True)
        source.set_property("pattern", index % 20)
        capsfilter.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw,width={tile_width},height={tile_height},framerate=30/1"
            ),
        )
        for element in (source, convert, scale, capsfilter):
            pipeline.add(element)
        source.link(convert)
        convert.link(scale)
        scale.link(capsfilter)
        pad = compositor.request_pad_simple("sink_%u")
        pad.set_property("xpos", (index % columns) * tile_width)
        pad.set_property("ypos", (index // columns) * tile_height)
        pad.set_property("width", tile_width)
        pad.set_property("height", tile_height)
        capsfilter.get_static_pad("src").link(pad)

        def count_frame(_: Any, __: Any, stream_index: int = index) -> Any:
            counters[stream_index] += 1
            return Gst.PadProbeReturn.OK

        probe_pad = capsfilter.get_static_pad("src")
        probe_id = probe_pad.add_probe(Gst.PadProbeType.BUFFER, count_frame)
        probes.append((probe_pad, probe_id))
    process = psutil.Process()
    process.cpu_percent(None)
    start_memory = process.memory_info().rss
    started = time.monotonic()
    if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
        raise BenchmarkUnavailable("Synthetic benchmark pipeline failed to start")
    samples: list[float] = []
    try:
        while time.monotonic() - started < duration_seconds:
            time.sleep(0.25)
            samples.append(process.cpu_percent(None))
    finally:
        pipeline.set_state(Gst.State.NULL)
        for pad, probe_id in probes:
            pad.remove_probe(probe_id)
    elapsed = max(0.001, time.monotonic() - started)
    end_memory = process.memory_info().rss
    capabilities = detect_capabilities()
    return {
        "platform": capabilities.get("pi_model") or capabilities.get("platform"),
        "output": f"{width}x{height}",
        "backend": "gstreamer-synthetic",
        "streams": streams,
        "source": "videotestsrc raw 30fps",
        "duration_seconds": round(elapsed, 2),
        "average_output_fps_per_stream": round(sum(counters) / streams / elapsed, 2),
        "frames_per_stream": counters,
        "process_cpu_percent_average": round(sum(samples) / len(samples), 2) if samples else 0,
        "memory_delta_bytes": end_memory - start_memory,
        "note": "Synthetic compositor benchmark; it does not measure RTSP network or codec decode cost.",
    }
