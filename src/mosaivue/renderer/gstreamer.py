from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit

from .base import HealthState, Rect, RendererBackend, RendererCapabilities, StreamHealth, StreamSpec

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class GStreamerUnavailable(RuntimeError):
    pass


def _import_gst() -> tuple[Any, Any, Any]:
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import GLib, GObject, Gst

        Gst.init(None)
        return Gst, GLib, GObject
    except (ImportError, ValueError) as exc:
        raise GStreamerUnavailable(
            "Install python3-gi, gir1.2-gstreamer-1.0 and GStreamer plugins"
        ) from exc


def _request_pad(element: Any, template: str) -> Any:
    """Request a pad on GStreamer releases before and after 1.20."""
    request = getattr(element, "request_pad_simple", None)
    if request is None:
        request = element.get_request_pad
    return request(template)


def _request_selector_pad(selector: Any) -> Any:
    pad = _request_pad(selector, "sink_%u")
    if pad is not None and pad.find_property("always-ok"):
        # Inactive live inputs must keep consuming frames. The default
        # NOT_LINKED flow result otherwise propagates into RTSP after a cut.
        pad.set_property("always-ok", True)
    return pad


@dataclass
class _SlotRuntime:
    spec: StreamSpec
    selector: Any
    selector_placeholder_pad: Any
    selector_camera_pad: Any | None
    placeholder_source: Any
    placeholder_caps: Any
    placeholder_text: Any
    queue: Any
    convert: Any
    cropper: Any
    scale: Any
    capsfilter: Any
    title_overlay: Any
    compositor_pad: Any
    source: Any | None = None
    source_queue: Any | None = None
    frame_probe_id: int | None = None
    reconnect_source_id: int | None = None
    prepared: _PreparedBranch | None = None
    failover_pending: bool = False
    restarting: bool = False
    recovery_source_id: int | None = None
    prepared_refresh_source_id: int | None = None
    source_refresh_source_id: int | None = None
    connect_started_monotonic: float | None = None
    retired_sources: list[Any] = field(default_factory=list)
    retired_queues: list[Any] = field(default_factory=list)
    retirement_warning_monotonic: float = 0.0
    recovery_warning_monotonic: float = 0.0


@dataclass
class _PreparedBranch:
    spec: StreamSpec
    source: Any
    queue: Any
    selector_pad: Any
    frame_probe_id: int
    frames: int = 0
    ready: bool = False
    last_frame_monotonic: float | None = None
    restarting: bool = False
    last_restart_monotonic: float = 0.0


class GStreamerRenderer(RendererBackend):
    """Single-pipeline GStreamer compositor with isolated, replaceable input branches."""

    def __init__(self, *, tls_ca_file: str | None = None) -> None:
        self.Gst, self.GLib, self.GObject = _import_gst()
        self._pipeline: Any | None = None
        self._compositor: Any | None = None
        self._sink: Any | None = None
        self._output_scale: Any | None = None
        self._output_caps: Any | None = None
        self._loop: Any | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._slots: dict[str, _SlotRuntime] = {}
        self._health: dict[str, StreamHealth] = {}
        self._output_width = 1920
        self._output_height = 1080
        self._sink_name = "auto"
        self._started_at: float | None = None
        self._bus_watch_id: int | None = None
        self._watchdog_source_id: int | None = None
        self._playing = False
        self._branch_sequence = 0
        self._failure_callback: Callable[[str], None] | None = None
        self._tls_ca_file = tls_ca_file
        self._tls_database: Any | None = None

    def set_failure_callback(self, callback: Callable[[str], None]) -> None:
        """Ask the controller to advance a rotation when its active source fails."""
        self._failure_callback = callback

    @classmethod
    def detect(cls) -> RendererCapabilities:
        try:
            Gst, _, _ = _import_gst()
        except GStreamerUnavailable as exc:
            return RendererCapabilities(name="gstreamer", available=False, reason=str(exc))
        required = [
            "compositor",
            "decodebin",
            "rtspsrc",
            "rtph264depay",
            "videotestsrc",
            "input-selector",
            "queue",
            "videoconvert",
            "videocrop",
            "aspectratiocrop",
            "videoscale",
            "capsfilter",
            "textoverlay",
        ]
        missing = [name for name in required if Gst.ElementFactory.find(name) is None]
        sinks = [
            name
            for name in ("kmssink", "waylandsink", "ximagesink", "fbdevsink", "autovideosink")
            if Gst.ElementFactory.find(name)
        ]
        decoders = [
            name
            for name in ("v4l2h264dec", "v4l2h265dec", "omxh264dec", "mppvideodec", "avdec_h264", "avdec_h265")
            if Gst.ElementFactory.find(name)
        ]
        return RendererCapabilities(
            name="gstreamer",
            available=not missing and bool(sinks),
            reason=f"Missing GStreamer elements: {', '.join(missing)}" if missing else None,
            sinks=sinks,
            decoders=decoders,
            dynamic_geometry=True,
            dynamic_source_replace=True,
            per_stream_recovery=True,
            snapshots=False,
            hardware_decode=any(name.startswith(("v4l2", "omx", "mpp")) for name in decoders),
        )

    def capabilities(self) -> RendererCapabilities:
        return self.detect()

    def initialize(self, *, width: int, height: int, sink: str = "auto") -> None:
        if self._thread and self._thread.is_alive():
            return
        self._output_width = width
        self._output_height = height
        self._sink_name = sink
        self._ready.clear()
        self._thread = threading.Thread(target=self._thread_main, name="mosaivue-gstreamer", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise TimeoutError("GStreamer renderer did not initialize")
        if self._startup_error:
            raise RuntimeError("GStreamer renderer initialization failed") from self._startup_error

    def _thread_main(self) -> None:
        try:
            self._loop = self.GLib.MainLoop()
            self._initialize_pipeline()
            self._ready.set()
            self._loop.run()
        except BaseException as exc:
            self._startup_error = exc
            LOGGER.exception("GStreamer main loop failed")
            self._ready.set()

    def _initialize_pipeline(self) -> None:
        Gst = self.Gst
        pipeline = Gst.Pipeline.new("mosaivue")
        compositor = Gst.ElementFactory.make("compositor", "wall")
        convert = Gst.ElementFactory.make("videoconvert", "output-convert")
        output_scale = Gst.ElementFactory.make("videoscale", "output-scale")
        output_caps = Gst.ElementFactory.make("capsfilter", "output-caps")
        sink = self._make_sink(self._sink_name)
        if not all((pipeline, compositor, convert, output_scale, output_caps, sink)):
            raise GStreamerUnavailable("Unable to create the GStreamer output pipeline")
        compositor.set_property("background", "black")
        if compositor.find_property("ignore-inactive-pads"):
            compositor.set_property("ignore-inactive-pads", True)
        if compositor.find_property("min-upstream-latency"):
            compositor.set_property("min-upstream-latency", 800_000_000)
        if compositor.find_property("latency"):
            compositor.set_property("latency", 100_000_000)
        output_caps.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw,width={self._output_width},height={self._output_height},framerate=5/1,pixel-aspect-ratio=1/1"
            ),
        )
        for element in (compositor, convert, output_scale, output_caps, sink):
            pipeline.add(element)
        if not compositor.link(convert) or not convert.link(output_scale) or not output_scale.link(output_caps) or not output_caps.link(sink):
            raise RuntimeError("Unable to link GStreamer compositor output")
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)
        self._pipeline = pipeline
        self._compositor = compositor
        self._sink = sink
        self._output_scale = output_scale
        self._output_caps = output_caps
        self._started_at = time.monotonic()
        self._watchdog_source_id = self.GLib.timeout_add_seconds(2, self._watchdog_tick)
        # Link the initial layout before KMS enters PLAYING. On some DRM
        # drivers, adding the first compositor pad to an already-playing empty
        # pipeline leaves the sink showing one frame and blocks upstream.

    def start_playback(self) -> None:
        self._call(self._start_playback)

    def _start_playback(self) -> None:
        if self._playing or self._pipeline is None:
            return
        result = self._pipeline.set_state(self.Gst.State.PLAYING)
        if result == self.Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("GStreamer output pipeline refused PLAYING state")
        self._playing = True
        # The slot placeholders are already linked to the compositor. Starting
        # every RTSP session and hardware decoder in the same state transition
        # can leave several sources stuck after their first frame on Rockchip.
        # Bring up one camera now, then give each remaining camera two seconds
        # before its initial source is opened. Normal layout edits stay eager.
        pending = [runtime for runtime in self._slots.values() if runtime.source is None]
        if not pending:
            return
        first = next((runtime for runtime in pending if runtime.spec.is_rotation), pending[0])
        self._start_initial_source(first)
        for index, runtime in enumerate((item for item in pending if item is not first), start=1):
            self.GLib.timeout_add_seconds(
                index * 2, self._start_delayed_source, runtime.spec.slot_id, runtime
            )

    def _start_delayed_source(self, slot_id: str, runtime: _SlotRuntime) -> bool:
        if self._playing and self._slots.get(slot_id) is runtime and runtime.source is None:
            self._start_initial_source(runtime)
        return False

    def _start_initial_source(self, runtime: _SlotRuntime) -> None:
        try:
            self._create_source_branch(runtime)
        except Exception:
            LOGGER.exception("Could not start initial camera source", extra={"slot_id": runtime.spec.slot_id})
            self._mark_offline(runtime.spec.slot_id, "Initial camera source failed")
            self._schedule_reconnect(runtime.spec.slot_id)

    def set_output_size(self, width: int, height: int) -> None:
        self._call(self._set_output_size, width, height)

    def _set_output_size(self, width: int, height: int) -> None:
        if width < 1 or height < 1:
            raise ValueError("Output dimensions must be positive")
        self._output_width = width
        self._output_height = height
        if self._output_caps is not None:
            self._output_caps.set_property(
                "caps",
                self.Gst.Caps.from_string(
                    f"video/x-raw,width={width},height={height},framerate=5/1,pixel-aspect-ratio=1/1"
                ),
            )

    def _make_sink(self, requested: str) -> Any:
        candidates: list[str]
        if requested != "auto":
            candidates = [requested]
        else:
            candidates = []
            if os.path.exists("/dev/dri/card0"):
                candidates.append("kmssink")
            if os.environ.get("WAYLAND_DISPLAY"):
                candidates.append("waylandsink")
            if os.environ.get("DISPLAY"):
                candidates.append("ximagesink")
            if os.path.exists("/dev/fb0"):
                candidates.append("fbdevsink")
            candidates.append("autovideosink")
        for name in candidates:
            sink = self.Gst.ElementFactory.make(name, "display")
            if sink:
                if sink.find_property("sync"):
                    sink.set_property("sync", False)
                if sink.find_property("force-modesetting") and name == "kmssink":
                    sink.set_property("force-modesetting", False)
                LOGGER.info("Selected GStreamer sink %s", name)
                return sink
        raise GStreamerUnavailable(f"No usable GStreamer sink found from {candidates}")

    def _call(self, function: Callable[..., T], *args: Any, timeout: float = 10, **kwargs: Any) -> T:
        if self._loop is None:
            raise RuntimeError("Renderer is not initialized")
        future: concurrent.futures.Future[T] = concurrent.futures.Future()

        def invoke() -> bool:
            try:
                future.set_result(function(*args, **kwargs))
            except BaseException as exc:
                future.set_exception(exc)
            return False

        self.GLib.idle_add(invoke)
        return future.result(timeout=timeout)

    def add_stream(self, spec: StreamSpec) -> None:
        self._call(self._add_stream, spec)

    def _add_stream(self, spec: StreamSpec) -> None:
        if spec.slot_id in self._slots:
            raise ValueError(f"Slot {spec.slot_id} already exists")
        assert self._pipeline is not None and self._compositor is not None
        Gst = self.Gst
        selector = Gst.ElementFactory.make("input-selector", f"selector-{spec.slot_id}")
        placeholder_source = Gst.ElementFactory.make("videotestsrc", f"placeholder-{spec.slot_id}")
        placeholder_caps = Gst.ElementFactory.make("capsfilter", f"placeholder-caps-{spec.slot_id}")
        placeholder_text = Gst.ElementFactory.make("textoverlay", f"placeholder-text-{spec.slot_id}")
        queue = Gst.ElementFactory.make("queue", f"post-queue-{spec.slot_id}")
        convert = Gst.ElementFactory.make("videoconvert", f"convert-{spec.slot_id}")
        cropper = Gst.ElementFactory.make("videocrop", f"manual-crop-{spec.slot_id}")
        scale = Gst.ElementFactory.make("videoscale", f"scale-{spec.slot_id}")
        capsfilter = Gst.ElementFactory.make("capsfilter", f"caps-{spec.slot_id}")
        title_overlay = Gst.ElementFactory.make("textoverlay", f"title-{spec.slot_id}")
        elements = [
            selector,
            placeholder_source,
            placeholder_caps,
            placeholder_text,
            queue,
            convert,
            cropper,
            scale,
            capsfilter,
            title_overlay,
        ]
        if not all(elements):
            raise RuntimeError("Required GStreamer slot elements are unavailable")
        # Each RTSP camera has its own live clock. Synchronizing an inactive
        # selector pad to the active stream can hold its decoder when that
        # stream pauses, eventually backing up the RTSP source.
        selector.set_property("sync-streams", False)
        placeholder_source.set_property("is-live", True)
        placeholder_source.set_property("pattern", "black")
        placeholder_caps.set_property(
            "caps", Gst.Caps.from_string("video/x-raw,width=640,height=360,framerate=5/1")
        )
        placeholder_text.set_property("text", f"{spec.camera_name}\nConnecting…")
        placeholder_text.set_property("valignment", "center")
        placeholder_text.set_property("halignment", "center")
        placeholder_text.set_property("font-desc", "Sans 18")
        queue.set_property("leaky", 2)
        queue.set_property("max-size-buffers", 2)
        title_overlay.set_property("font-desc", "Sans 14")
        title_overlay.set_property("shaded-background", True)
        for element in elements:
            self._pipeline.add(element)
        if not placeholder_source.link(placeholder_caps) or not placeholder_caps.link(placeholder_text):
            raise RuntimeError("Unable to link placeholder branch")
        placeholder_pad = _request_selector_pad(selector)
        if placeholder_pad is None:
            raise RuntimeError("Unable to request placeholder selector pad")
        if placeholder_text.get_static_pad("src").link(placeholder_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError("Unable to connect placeholder branch to selector")
        chain = [selector, queue, convert, cropper, scale, capsfilter, title_overlay]
        for first, second in zip(chain, chain[1:], strict=False):
            if not first.link(second):
                raise RuntimeError(f"Unable to link slot element {first.name} to {second.name}")
        compositor_pad = _request_pad(self._compositor, "sink_%u")
        if compositor_pad is None:
            raise RuntimeError("Unable to request compositor pad")
        if title_overlay.get_static_pad("src").link(compositor_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError("Unable to connect slot to compositor")
        runtime = _SlotRuntime(
            spec=spec,
            selector=selector,
            selector_placeholder_pad=placeholder_pad,
            selector_camera_pad=None,
            placeholder_source=placeholder_source,
            placeholder_caps=placeholder_caps,
            placeholder_text=placeholder_text,
            queue=queue,
            convert=convert,
            cropper=cropper,
            scale=scale,
            capsfilter=capsfilter,
            title_overlay=title_overlay,
            compositor_pad=compositor_pad,
        )
        self._slots[spec.slot_id] = runtime
        self._health[spec.slot_id] = StreamHealth(slot_id=spec.slot_id, camera_id=spec.camera_id)
        self._apply_geometry(runtime)
        self._apply_label(runtime)
        selector.set_property("active-pad", placeholder_pad)
        for element in elements:
            element.sync_state_with_parent()
        if self._playing:
            self._create_source_branch(runtime)

    def _create_source_branch(self, runtime: _SlotRuntime) -> None:
        Gst = self.Gst
        assert self._pipeline is not None
        self._branch_sequence += 1
        name = f"{runtime.spec.slot_id}-{self._branch_sequence}"
        source_queue = Gst.ElementFactory.make("queue", f"source-queue-{name}")
        if not source_queue:
            raise RuntimeError("Unable to create RTSP source branch")
        source = self._new_video_source(runtime.spec, name, source_queue)
        source_queue.set_property("leaky", 2)
        source_queue.set_property("max-size-buffers", 2)
        self._pipeline.add(source)
        self._pipeline.add(source_queue)
        camera_pad = _request_selector_pad(runtime.selector)
        if camera_pad is None:
            raise RuntimeError("Unable to request camera selector pad")
        if source_queue.get_static_pad("src").link(camera_pad) != Gst.PadLinkReturn.OK:
            raise RuntimeError("Unable to link camera queue to selector")
        runtime.source = source
        runtime.source_queue = source_queue
        runtime.selector_camera_pad = camera_pad
        runtime.connect_started_monotonic = time.monotonic()
        probe_pad = source_queue.get_static_pad("src")
        runtime.frame_probe_id = probe_pad.add_probe(
            Gst.PadProbeType.BUFFER, self._on_frame, runtime.spec.slot_id, source_queue
        )
        source_queue.sync_state_with_parent()
        source.sync_state_with_parent()
        health = self._health[runtime.spec.slot_id]
        health.state = HealthState.connecting
        health.detail = "Connecting to camera"

    def prepare_stream(self, slot_id: str, spec: StreamSpec) -> None:
        self._call(self._prepare_stream, slot_id, spec)

    def _prepare_stream(self, slot_id: str, spec: StreamSpec) -> None:
        runtime = self._require_slot(slot_id)
        prepared = runtime.prepared
        if prepared and (prepared.spec.camera_id, prepared.spec.stream_profile_id, prepared.spec.url) == (
            spec.camera_id, spec.stream_profile_id, spec.url
        ):
            if not prepared.ready or not prepared.last_frame_monotonic or time.monotonic() - prepared.last_frame_monotonic > 8:
                self._restart_prepared(slot_id, prepared)
                self._schedule_prepared_refresh(slot_id, prepared)
            return
        self._cancel_prepared(slot_id)
        assert self._pipeline is not None
        Gst = self.Gst
        self._branch_sequence += 1
        name = f"{slot_id}-{self._branch_sequence}"
        queue = Gst.ElementFactory.make("queue", f"prepared-queue-{name}")
        if not queue:
            raise RuntimeError("Unable to create prepared RTSP branch")
        source = self._new_video_source(spec, f"prepared-{name}", queue)
        queue.set_property("leaky", 2)
        queue.set_property("max-size-buffers", 2)
        source_added = self._pipeline.add(source)
        queue_added = self._pipeline.add(queue)
        if not source_added or not queue_added:
            if source_added:
                self._pipeline.remove(source)
            if queue_added:
                self._pipeline.remove(queue)
            raise RuntimeError("Unable to add prepared RTSP branch to pipeline")
        selector_pad = _request_selector_pad(runtime.selector)
        if selector_pad is None:
            self._pipeline.remove(source)
            self._pipeline.remove(queue)
            raise RuntimeError("Unable to request prepared selector pad")
        if queue.get_static_pad("src").link(selector_pad) != Gst.PadLinkReturn.OK:
            runtime.selector.release_request_pad(selector_pad)
            self._pipeline.remove(source)
            self._pipeline.remove(queue)
            raise RuntimeError("Unable to link prepared source to selector")
        probe_id = queue.get_static_pad("src").add_probe(
            Gst.PadProbeType.BUFFER, self._on_prepared_frame, slot_id, queue
        )
        runtime.prepared = _PreparedBranch(spec, source, queue, selector_pad, probe_id)
        queue.sync_state_with_parent()
        source.sync_state_with_parent()

    def _on_prepared_frame(self, _: Any, __: Any, slot_id: str, queue: Any) -> Any:
        runtime = self._slots.get(slot_id)
        if runtime and runtime.prepared and runtime.prepared.queue == queue and not runtime.prepared.restarting:
            runtime.prepared.frames += 1
            runtime.prepared.ready = True
            runtime.prepared.last_frame_monotonic = time.monotonic()
            health = self._health.get(slot_id)
            if health and health.state == HealthState.stalled:
                self._request_failover(slot_id)
        return self.Gst.PadProbeReturn.OK

    def cancel_prepared(self, slot_id: str) -> None:
        self._call(self._cancel_prepared, slot_id)

    def _cancel_prepared(self, slot_id: str) -> None:
        runtime = self._slots.get(slot_id)
        if not runtime or not runtime.prepared or self._pipeline is None:
            return
        prepared = runtime.prepared
        runtime.prepared = None
        prepared.queue.get_static_pad("src").remove_probe(prepared.frame_probe_id)
        for element in (prepared.source, prepared.queue):
            element.set_state(self.Gst.State.NULL)
            self._pipeline.remove(element)
        runtime.selector.release_request_pad(prepared.selector_pad)

    def _configure_rtsp_source(self, source: Any, spec: StreamSpec) -> None:
        latency_map = {"ultra-low": 50, "low": 120, "normal": 300, "stable": 800}
        scheme = urlsplit(spec.url).scheme.lower()
        if scheme == "rtsps" and self._tls_ca_file and source.find_property("tls-database"):
            if self._tls_database is None:
                from gi.repository import Gio

                self._tls_database = Gio.TlsFileDatabase.new(self._tls_ca_file)
            source.set_property("tls-database", self._tls_database)
        if source.find_property("latency"):
            source.set_property("latency", latency_map.get(spec.latency_profile, 120))
        if source.find_property("drop-on-latency"):
            source.set_property("drop-on-latency", spec.latency_profile in {"ultra-low", "low"})
        if source.find_property("protocols"):
            # GstRtsp.RTSPLowerTrans enum values: UDP=1, UDP_MCAST=2, TCP=4.
            if scheme == "rtsps" or spec.transport == "tcp":
                source.set_property("protocols", 4)
            elif spec.transport == "udp":
                source.set_property("protocols", 1)

    def _new_video_source(self, spec: StreamSpec, name: str, queue: Any) -> Any:
        Gst = self.Gst
        if urlsplit(spec.url).scheme.lower() not in {"rtsp", "rtsps"}:
            raise ValueError("GStreamer camera sources must use RTSP or RTSPS")
        source = Gst.Bin.new(f"{name}-source")
        rtsp = Gst.ElementFactory.make("rtspsrc", f"{name}-rtsp")
        decoder = Gst.ElementFactory.make("decodebin", f"{name}-decode")
        if source is None or rtsp is None or decoder is None:
            raise RuntimeError("Unable to create RTSP video source")
        rtsp.set_property("location", spec.url)
        self._configure_rtsp_source(rtsp, spec)
        # UniFi and other cameras can advertise audio alongside video. Select
        # only video before SETUP for fixed and rotating tiles alike so unused
        # audio tracks cannot stall the RTSP session during cold start.
        rtsp.connect("select-stream", self._select_video_rtsp_stream)
        source.add(rtsp)
        source.add(decoder)
        rtsp.connect("pad-added", self._on_rtp_pad_added, spec.slot_id, source, decoder)
        decoder.connect("pad-added", self._on_decoded_video_pad, spec.slot_id, source, queue)
        decoder.connect("pad-removed", self._on_decoded_video_pad_removed, source)
        return source

    @staticmethod
    def _select_video_rtsp_stream(_: Any, __: int, caps: Any) -> bool:
        structure = caps.get_structure(0) if caps and caps.get_size() else None
        return bool(structure and structure.get_string("media") == "video")

    def _on_decoded_video_pad(self, _: Any, pad: Any, slot_id: str, source: Any, queue: Any) -> None:
        caps = pad.get_current_caps() or pad.query_caps(None)
        if not caps or not caps.to_string().startswith("video/"):
            return
        existing = source.get_static_pad("src")
        if existing:
            if not existing.set_target(pad):
                LOGGER.warning("Could not relink decoded video for slot %s", slot_id)
            return
        ghost = self.Gst.GhostPad.new("src", pad)
        ghost.set_active(True)
        if source.add_pad(ghost):
            self._on_source_pad_added(source, ghost, slot_id, queue)

    def _on_decoded_video_pad_removed(self, _: Any, pad: Any, source: Any) -> None:
        ghost = source.get_static_pad("src")
        if ghost and ghost.get_target() == pad:
            ghost.set_target(None)

    def _on_rtp_pad_added(self, _: Any, pad: Any, slot_id: str, source: Any, decoder: Any) -> None:
        caps = pad.get_current_caps() or pad.query_caps(None)
        structure = caps.get_structure(0) if caps and caps.get_size() else None
        if structure is None or structure.get_string("media") != "video":
            return
        decoder_sink = decoder.get_static_pad("sink")
        if decoder_sink.is_linked():
            peer = decoder_sink.get_peer()
            depay = peer.get_parent_element() if peer else None
            depay_sink = depay.get_static_pad("sink") if depay else None
            if depay_sink and not depay_sink.is_linked():
                result = pad.link(depay_sink)
                if result != self.Gst.PadLinkReturn.OK:
                    LOGGER.warning("Could not reconnect RTSP video for slot %s: %s", slot_id, result)
            return
        encoding = (structure.get_string("encoding-name") or "").upper()
        depay_factory = {"H264": "rtph264depay", "H265": "rtph265depay", "JPEG": "rtpjpegdepay"}.get(encoding)
        if depay_factory is None:
            LOGGER.warning("Unsupported RTSP video encoding %s for slot %s", encoding, slot_id)
            return
        depay = self.Gst.ElementFactory.make(depay_factory)
        if depay is None or not source.add(depay):
            LOGGER.warning("Could not create RTSP depayloader for slot %s", slot_id)
            return
        if not depay.link(decoder) or pad.link(depay.get_static_pad("sink")) != self.Gst.PadLinkReturn.OK:
            LOGGER.warning("Could not link RTSP video for slot %s", slot_id)
            depay.set_state(self.Gst.State.NULL)
            source.remove(depay)
            return
        depay.sync_state_with_parent()

    def _on_source_pad_added(self, _: Any, pad: Any, slot_id: str, branch_queue: Any | None = None) -> None:
        runtime = self._slots.get(slot_id)
        queue = branch_queue or (runtime.source_queue if runtime else None)
        if not runtime or not queue:
            return
        if queue != runtime.source_queue and (not runtime.prepared or runtime.prepared.queue != queue):
            return
        caps = pad.get_current_caps() or pad.query_caps(None)
        if not caps or not caps.to_string().startswith("video/"):
            return
        sink_pad = queue.get_static_pad("sink")
        if not sink_pad.is_linked():
            result = pad.link(sink_pad)
            if result != self.Gst.PadLinkReturn.OK:
                self._mark_offline(slot_id, f"Video pad link failed: {result.value_nick}")

    def _on_frame(self, pad: Any, __: Any, slot_id: str, queue: Any) -> Any:
        runtime = self._slots.get(slot_id)
        health = self._health.get(slot_id)
        if runtime and health and runtime.source_queue == queue:
            health.last_frame_monotonic = time.monotonic()
            health.decoded_frames += 1
            health.detail = None
            if runtime.spec.source_width is None or runtime.spec.source_height is None:
                caps = pad.get_current_caps()
                structure = caps.get_structure(0) if caps and caps.get_size() else None
                if structure:
                    width = structure.get_value("width")
                    height = structure.get_value("height")
                    if isinstance(width, int) and isinstance(height, int):
                        runtime.spec.source_width = width
                        runtime.spec.source_height = height
                        self.GLib.idle_add(self._apply_geometry, runtime)
            if health.state != HealthState.live:
                health.state = HealthState.live
                health.reconnect_backoff_seconds = 1.0
                self.GLib.idle_add(self._activate_camera_pad, slot_id)
        return self.Gst.PadProbeReturn.OK

    def _activate_camera_pad(self, slot_id: str) -> bool:
        runtime = self._slots.get(slot_id)
        health = self._health.get(slot_id)
        if runtime and health and health.state == HealthState.live and runtime.selector_camera_pad:
            runtime.selector.set_property("active-pad", runtime.selector_camera_pad)
        return False

    def _apply_geometry(self, runtime: _SlotRuntime) -> None:
        rect = runtime.spec.rect
        pad = runtime.compositor_pad
        for property_name, value in (
            ("xpos", rect.x),
            ("ypos", rect.y),
            ("width", rect.width),
            ("height", rect.height),
            ("zorder", runtime.spec.z_index),
            ("alpha", runtime.spec.opacity),
        ):
            if pad.find_property(property_name):
                pad.set_property(property_name, value)
        if pad.find_property("sizing-policy"):
            # 1 is keep-aspect-ratio in GstVideo.VideoAggregatorPad.
            pad.set_property("sizing-policy", 1 if runtime.spec.aspect_mode in {"contain", "native"} else 0)
        crop = runtime.spec.crop or {}
        source_width = runtime.spec.source_width
        source_height = runtime.spec.source_height
        crop_pixels = {"top": 0, "right": 0, "bottom": 0, "left": 0}
        if source_width and source_height:
            crop_pixels = {
                "top": round(float(crop.get("top", 0)) * source_height),
                "right": round(float(crop.get("right", 0)) * source_width),
                "bottom": round(float(crop.get("bottom", 0)) * source_height),
                "left": round(float(crop.get("left", 0)) * source_width),
            }
            crop_pixels["left"] = min(crop_pixels["left"], max(0, source_width - 2))
            crop_pixels["right"] = min(
                crop_pixels["right"], max(0, source_width - crop_pixels["left"] - 1)
            )
            crop_pixels["top"] = min(crop_pixels["top"], max(0, source_height - 2))
            crop_pixels["bottom"] = min(
                crop_pixels["bottom"], max(0, source_height - crop_pixels["top"] - 1)
            )
        if source_width and source_height and runtime.spec.aspect_mode == "cover":
            available_width = source_width - crop_pixels["left"] - crop_pixels["right"]
            available_height = source_height - crop_pixels["top"] - crop_pixels["bottom"]
            if available_width * rect.height > available_height * rect.width:
                excess = available_width - round(available_height * rect.width / rect.height)
                crop_pixels["left"] += excess // 2
                crop_pixels["right"] += excess - excess // 2
            else:
                excess = available_height - round(available_width * rect.height / rect.width)
                crop_pixels["top"] += excess // 2
                crop_pixels["bottom"] += excess - excess // 2
        for property_name, value in crop_pixels.items():
            runtime.cropper.set_property(property_name, value)

        if runtime.spec.aspect_mode in {"cover", "stretch"}:
            runtime.capsfilter.set_property(
                "caps",
                self.Gst.Caps.from_string(
                    f"video/x-raw,width={rect.width},height={rect.height},pixel-aspect-ratio=1/1"
                ),
            )
        else:
            runtime.capsfilter.set_property("caps", None)

    def remove_stream(self, slot_id: str) -> None:
        self._call(self._remove_stream, slot_id)

    def _remove_stream(self, slot_id: str) -> None:
        self._cancel_prepared(slot_id)
        runtime = self._slots.pop(slot_id, None)
        self._health.pop(slot_id, None)
        if runtime is None or self._pipeline is None or self._compositor is None:
            return
        self._remove_source_branch(runtime)
        elements = [
            runtime.placeholder_source,
            runtime.placeholder_caps,
            runtime.placeholder_text,
            runtime.selector,
            runtime.queue,
            runtime.convert,
            runtime.cropper,
            runtime.scale,
            runtime.capsfilter,
            runtime.title_overlay,
        ]
        for element in [item for item in elements if item is not None]:
            element.set_state(self.Gst.State.NULL)
            self._pipeline.remove(element)
        runtime.selector.release_request_pad(runtime.selector_placeholder_pad)
        self._compositor.release_request_pad(runtime.compositor_pad)

    def _remove_source_branch(self, runtime: _SlotRuntime) -> None:
        if self._pipeline is None:
            return
        if runtime.reconnect_source_id:
            self.GLib.source_remove(runtime.reconnect_source_id)
            runtime.reconnect_source_id = None
        if runtime.source_queue and runtime.frame_probe_id:
            runtime.source_queue.get_static_pad("src").remove_probe(runtime.frame_probe_id)
        for element in (runtime.source, runtime.source_queue):
            if element:
                element.set_state(self.Gst.State.NULL)
                self._pipeline.remove(element)
        if runtime.selector_camera_pad:
            runtime.selector.release_request_pad(runtime.selector_camera_pad)
        runtime.source = None
        runtime.source_queue = None
        runtime.selector_camera_pad = None
        runtime.frame_probe_id = None

    def replace_stream(self, slot_id: str, spec: StreamSpec) -> None:
        self._call(self._replace_stream, slot_id, spec)

    def activate_prepared_stream(self, slot_id: str, spec: StreamSpec) -> None:
        self._call(self._replace_stream, slot_id, spec, True)

    def _replace_stream(self, slot_id: str, spec: StreamSpec, require_prepared: bool = False) -> None:
        runtime = self._slots.get(slot_id)
        if runtime is None:
            self._add_stream(spec)
            return
        prepared = runtime.prepared
        if prepared and (prepared.spec.camera_id, prepared.spec.stream_profile_id, prepared.spec.url) == (
            spec.camera_id, spec.stream_profile_id, spec.url
        ):
            if not prepared.ready or not prepared.last_frame_monotonic or time.monotonic() - prepared.last_frame_monotonic > 8:
                raise RuntimeError("Replacement stream is still connecting")
            previous_health = self._health[slot_id]
            old = _PreparedBranch(
                runtime.spec, runtime.source, runtime.source_queue, runtime.selector_camera_pad,
                runtime.frame_probe_id, previous_health.decoded_frames,
                previous_health.state == HealthState.live,
                previous_health.last_frame_monotonic,
            )
            runtime.selector.set_property("active-pad", prepared.selector_pad)
            old.queue.get_static_pad("src").remove_probe(old.frame_probe_id)
            prepared.queue.get_static_pad("src").remove_probe(prepared.frame_probe_id)
            old.frame_probe_id = old.queue.get_static_pad("src").add_probe(
                self.Gst.PadProbeType.BUFFER, self._on_prepared_frame, slot_id, old.queue
            )
            runtime.source = prepared.source
            runtime.source_queue = prepared.queue
            runtime.selector_camera_pad = prepared.selector_pad
            runtime.frame_probe_id = prepared.queue.get_static_pad("src").add_probe(
                self.Gst.PadProbeType.BUFFER, self._on_frame, slot_id, prepared.queue
            )
            runtime.prepared = old
            runtime.failover_pending = False
            runtime.spec = spec
            self._health[slot_id] = StreamHealth(
                slot_id=slot_id, camera_id=spec.camera_id, state=HealthState.live,
                last_frame_monotonic=prepared.last_frame_monotonic,
                decoded_frames=prepared.frames,
                restart_count=previous_health.restart_count,
                switch_count=previous_health.switch_count + int(old.spec.camera_id != spec.camera_id),
                last_restart_reason=previous_health.last_restart_reason,
            )
            self._apply_geometry(runtime)
            self._apply_label(runtime)
            return
        if require_prepared:
            raise RuntimeError("Replacement stream has not been prepared")
        self._cancel_prepared(slot_id)
        runtime.selector.set_property("active-pad", runtime.selector_placeholder_pad)
        runtime.placeholder_text.set_property("text", f"{spec.camera_name}\nConnecting…")
        previous_health = self._health[slot_id]
        switched = runtime.spec.camera_id != spec.camera_id
        self._remove_source_branch(runtime)
        runtime.spec = spec
        self._health[slot_id] = StreamHealth(
            slot_id=slot_id, camera_id=spec.camera_id,
            restart_count=previous_health.restart_count,
            switch_count=previous_health.switch_count + int(switched),
            last_restart_reason=previous_health.last_restart_reason,
        )
        self._apply_geometry(runtime)
        self._apply_label(runtime)
        self._create_source_branch(runtime)

    def move_stream(self, slot_id: str, rect: Rect) -> None:
        self._call(self._change_geometry, slot_id, rect)

    def resize_stream(self, slot_id: str, rect: Rect) -> None:
        self._call(self._change_geometry, slot_id, rect)

    def _change_geometry(self, slot_id: str, rect: Rect) -> None:
        runtime = self._require_slot(slot_id)
        runtime.spec.rect = rect
        self._apply_geometry(runtime)

    def set_crop_mode(self, slot_id: str, aspect_mode: str, crop: dict[str, float] | None = None) -> None:
        self._call(self._set_crop_mode, slot_id, aspect_mode, crop or {})

    def _set_crop_mode(self, slot_id: str, aspect_mode: str, crop: dict[str, float]) -> None:
        runtime = self._require_slot(slot_id)
        runtime.spec.aspect_mode = aspect_mode
        runtime.spec.crop = crop
        self._apply_geometry(runtime)

    def set_visibility(self, slot_id: str, visible: bool) -> None:
        self._call(self._set_visibility, slot_id, visible)

    def _set_visibility(self, slot_id: str, visible: bool) -> None:
        runtime = self._require_slot(slot_id)
        if runtime.compositor_pad.find_property("alpha"):
            runtime.compositor_pad.set_property("alpha", runtime.spec.opacity if visible else 0.0)

    def set_opacity(self, slot_id: str, opacity: float) -> None:
        self._call(self._set_opacity, slot_id, opacity)

    def _set_opacity(self, slot_id: str, opacity: float) -> None:
        runtime = self._require_slot(slot_id)
        runtime.spec.opacity = max(0.0, min(1.0, opacity))
        if runtime.compositor_pad.find_property("alpha"):
            runtime.compositor_pad.set_property("alpha", runtime.spec.opacity)

    def set_label(self, slot_id: str, label: str | None, title_position: str) -> None:
        self._call(self._set_label, slot_id, label, title_position)

    def _set_label(self, slot_id: str, label: str | None, title_position: str) -> None:
        runtime = self._require_slot(slot_id)
        runtime.spec.label = label
        runtime.spec.title_position = title_position
        self._apply_label(runtime)

    def _apply_label(self, runtime: _SlotRuntime) -> None:
        position = runtime.spec.title_position
        text = runtime.spec.label or ""
        if position == "none":
            text = ""
        alignments = {
            "top-left": ("top", "left"),
            "top-right": ("top", "right"),
            "bottom-left": ("bottom", "left"),
            "bottom-right": ("bottom", "right"),
        }
        vertical, horizontal = alignments.get(position, ("bottom", "left"))
        runtime.title_overlay.set_property("text", text)
        runtime.title_overlay.set_property("valignment", vertical)
        runtime.title_overlay.set_property("halignment", horizontal)
        if runtime.title_overlay.find_property("silent"):
            runtime.title_overlay.set_property("silent", not bool(text))

    def set_z_order(self, slot_id: str, z_index: int) -> None:
        self._call(self._set_z_order, slot_id, z_index)

    def _set_z_order(self, slot_id: str, z_index: int) -> None:
        runtime = self._require_slot(slot_id)
        runtime.spec.z_index = z_index
        if runtime.compositor_pad.find_property("zorder"):
            runtime.compositor_pad.set_property("zorder", z_index)

    def snapshot(self, slot_id: str | None = None) -> bytes | None:
        return None

    def health(self) -> dict[str, Any]:
        return self._call(self._health_snapshot)

    def _health_snapshot(self) -> dict[str, Any]:
        return {
            "backend": "gstreamer",
            "state": "RUNNING" if self._playing else "READY" if self._pipeline is not None else "STOPPED",
            "sink": self._sink.get_factory().get_name() if self._sink else None,
            "output": {"width": self._output_width, "height": self._output_height},
            "uptime_seconds": time.monotonic() - self._started_at if self._started_at else 0,
            "streams": {key: value.to_dict() for key, value in self._health.items()},
        }

    def restart_stream(self, slot_id: str) -> None:
        self._call(self._restart_stream, slot_id)

    def _restart_stream(self, slot_id: str) -> None:
        runtime = self._require_slot(slot_id)
        if runtime.restarting:
            return
        health = self._health[slot_id]
        health.restart_count += 1
        health.last_restart_reason = "Player recovery or manual restart"
        health.state = HealthState.reconnecting
        runtime.selector.set_property("active-pad", runtime.selector_placeholder_pad)
        runtime.placeholder_text.set_property("text", f"{runtime.spec.camera_name}\nReconnecting…")
        if runtime.source is None:
            self._create_source_branch(runtime)
            return
        runtime.restarting = True
        source = runtime.source

        def stop_source(element: Any, _: Any) -> None:
            try:
                element.set_state(self.Gst.State.NULL)
            except Exception:
                LOGGER.exception("Could not stop failed stream", extra={"slot_id": slot_id})

            def resume() -> bool:
                current = self._slots.get(slot_id)
                if current is runtime and current.source is source:
                    runtime.restarting = False
                    source.sync_state_with_parent()
                return False

            self.GLib.timeout_add_seconds(1, resume)

        source.call_async(stop_source, None)
        self._schedule_source_refresh(slot_id, runtime, source)

    def _schedule_source_refresh(self, slot_id: str, runtime: _SlotRuntime, source: Any) -> None:
        if runtime.source_refresh_source_id:
            return

        def refresh() -> bool:
            current = self._slots.get(slot_id)
            if current is not runtime:
                return False
            runtime.source_refresh_source_id = None
            if runtime.source is not source:
                return False
            health = self._health.get(slot_id)
            if health and health.state == HealthState.live and health.last_frame_monotonic and time.monotonic() - health.last_frame_monotonic < 8:
                return False
            if len(runtime.retired_sources) >= 2:
                LOGGER.warning("Waiting for retired fixed camera branches to stop", extra={"slot_id": slot_id})
                self._schedule_source_refresh(slot_id, runtime, source)
                return False
            LOGGER.warning("Opening a fresh fixed camera source", extra={"slot_id": slot_id})
            self._retire_branch(
                runtime, source, runtime.source_queue, runtime.selector_camera_pad,
                runtime.frame_probe_id,
            )
            runtime.source = None
            runtime.source_queue = None
            runtime.selector_camera_pad = None
            runtime.frame_probe_id = None
            runtime.restarting = False
            try:
                self._create_source_branch(runtime)
            except Exception:
                LOGGER.exception("Could not open fresh fixed camera source", extra={"slot_id": slot_id})
            return False

        runtime.source_refresh_source_id = self.GLib.timeout_add_seconds(10, refresh)

    def _require_slot(self, slot_id: str) -> _SlotRuntime:
        runtime = self._slots.get(slot_id)
        if runtime is None:
            raise KeyError(f"Renderer slot {slot_id} not found")
        return runtime

    def _watchdog_tick(self) -> bool:
        now = time.monotonic()
        for slot_id, health in list(self._health.items()):
            runtime = self._slots.get(slot_id)
            if (
                runtime
                and health.state in (HealthState.connecting, HealthState.reconnecting)
                and runtime.connect_started_monotonic is not None
                and now - runtime.connect_started_monotonic > 20
                and not runtime.restarting
                and not runtime.source_refresh_source_id
                and not runtime.reconnect_source_id
            ):
                prepared = runtime.prepared
                if (
                    prepared and prepared.ready and prepared.last_frame_monotonic
                    and now - prepared.last_frame_monotonic < 8
                    and self._request_failover(slot_id)
                ):
                    continue
                self._mark_offline(slot_id, "No first video frame received within 20 seconds")
                self._schedule_reconnect(slot_id)
                continue
            if (
                health.state == HealthState.live
                and health.last_frame_monotonic
                and now - health.last_frame_monotonic > 8
            ):
                if self._request_failover(slot_id):
                    continue
                health.state = HealthState.stalled
                health.detail = "No video frames received for 8 seconds"
                self._mark_offline(slot_id, health.detail)
                self._schedule_reconnect(slot_id)
        return True

    def _request_failover(self, slot_id: str) -> bool:
        runtime = self._slots.get(slot_id)
        prepared = runtime.prepared if runtime else None
        if not runtime or not prepared or not self._failure_callback:
            return False
        if runtime.failover_pending:
            return True
        if not prepared.ready or not prepared.last_frame_monotonic or time.monotonic() - prepared.last_frame_monotonic > 8:
            # A rotation branch must never be torn down from the bus callback:
            # GStreamer can block its own main loop while stopping RTSP there.
            # The active RTSP pad has stopped advancing. Select the live
            # placeholder so input-selector's running time keeps advancing
            # while the replacement branch is opened.
            health = self._health.get(slot_id)
            if health:
                health.state = HealthState.stalled
                health.detail = "Both rotation feeds unavailable; recovery pending"
            runtime.selector.set_property("active-pad", runtime.selector_placeholder_pad)
            runtime.placeholder_text.set_property(
                "text", f"{runtime.spec.camera_name}\nReconnecting…"
            )
            self._arm_rotation_recovery(slot_id)
            return True
        runtime.failover_pending = True

        def allow_retry() -> bool:
            current = self._slots.get(slot_id)
            if current:
                current.failover_pending = False
            return False

        self.GLib.timeout_add_seconds(5, allow_retry)
        try:
            self._failure_callback(slot_id)
        except Exception:
            runtime.failover_pending = False
            LOGGER.exception("Could not request prepared rotation failover", extra={"slot_id": slot_id})
            return False
        return True

    def _arm_rotation_recovery(self, slot_id: str) -> None:
        runtime = self._slots.get(slot_id)
        if not runtime or runtime.recovery_source_id:
            return

        def recover_or_restart() -> bool:
            current = self._slots.get(slot_id)
            if not current:
                return False
            current.recovery_source_id = None
            health = self._health.get(slot_id)
            if health and health.last_frame_monotonic and time.monotonic() - health.last_frame_monotonic < 8:
                return False
            prepared = current.prepared
            if prepared and prepared.ready and prepared.last_frame_monotonic and time.monotonic() - prepared.last_frame_monotonic < 8:
                self._request_failover(slot_id)
                self._arm_rotation_recovery(slot_id)
                return False
            if not current.restarting and not current.source_refresh_source_id and not current.reconnect_source_id:
                LOGGER.warning("Retrying unavailable rotation camera", extra={"slot_id": slot_id})
                self._restart_stream(slot_id)
            if self._started_at is not None and time.monotonic() - self._started_at < 60:
                self._arm_rotation_recovery(slot_id)
                return False
            now = time.monotonic()
            if now - getattr(current, "recovery_warning_monotonic", 0.0) >= 60:
                LOGGER.error("Both rotation sources remained unavailable", extra={"slot_id": slot_id})
                current.recovery_warning_monotonic = now
            self._restart_renderer_with_cooldown(slot_id, "both rotation sources failed")
            # Keep healthy fixed tiles running through short camera outages,
            # but do not leave a rotation tile black indefinitely when both
            # sessions fail to recover despite repeated per-stream retries.
            last_frame = health.last_frame_monotonic if health else None
            if now - (last_frame or self._started_at or now) >= 120:
                self._restart_renderer_with_cooldown(
                    slot_id, "both rotation sources stalled for two minutes",
                    allow_healthy_others=True, cooldown_seconds=1800,
                )
            self._arm_rotation_recovery(slot_id)
            return False

        runtime.recovery_source_id = self.GLib.timeout_add_seconds(15, recover_or_restart)

    def _mark_offline(self, slot_id: str, detail: str) -> None:
        runtime = self._slots.get(slot_id)
        health = self._health.get(slot_id)
        if not runtime or not health:
            return
        health.state = HealthState.offline
        health.detail = detail
        runtime.placeholder_text.set_property("text", f"{runtime.spec.camera_name}\nStream unavailable\nReconnecting…")
        runtime.selector.set_property("active-pad", runtime.selector_placeholder_pad)

    def _schedule_reconnect(self, slot_id: str) -> None:
        runtime = self._slots.get(slot_id)
        health = self._health.get(slot_id)
        if not runtime or not health or runtime.reconnect_source_id:
            return
        delay = max(1, min(60, round(health.reconnect_backoff_seconds)))
        health.reconnect_backoff_seconds = min(60.0, health.reconnect_backoff_seconds * 2)

        def reconnect() -> bool:
            runtime.reconnect_source_id = None
            try:
                self._restart_stream(slot_id)
            except Exception:
                LOGGER.exception("Per-stream reconnect failed", extra={"slot_id": slot_id})
                self._schedule_reconnect(slot_id)
            return False

        runtime.reconnect_source_id = self.GLib.timeout_add_seconds(delay, reconnect)

    def _on_bus_message(self, _: Any, message: Any) -> None:
        if message.type in (self.Gst.MessageType.ERROR, self.Gst.MessageType.WARNING, self.Gst.MessageType.EOS):
            slot_id = self._slot_for_element(message.src)
            if slot_id and self._is_retired_message(message.src, slot_id):
                return
            if slot_id and self._is_placeholder_message(message.src, slot_id):
                LOGGER.debug("Ignoring inactive placeholder message for slot %s", slot_id)
                return
        if message.type == self.Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            slot_id = self._slot_for_element(message.src)
            factory = message.src.get_factory() if hasattr(message.src, "get_factory") else None
            origin = factory.get_name() if factory else type(message.src).__name__
            match = re.search(r"reason [a-zA-Z_-]+ \(-?\d+\)", debug or "")
            reason = match.group(0) if match else "unknown"
            if slot_id:
                if self._is_prepared_message(message.src, slot_id):
                    LOGGER.warning(
                        "Prepared GStreamer stream error for slot %s from %s (%s): %s",
                        slot_id, origin, reason, error.message,
                    )
                    self._mark_prepared_unavailable(slot_id)
                    return
                LOGGER.warning(
                    "GStreamer stream error for slot %s from %s (%s): %s",
                    slot_id,
                    origin,
                    reason,
                    error.message,
                    extra={"slot_id": slot_id},
                )
                if self._request_failover(slot_id):
                    return
                self._mark_offline(slot_id, error.message)
                self._schedule_reconnect(slot_id)
            else:
                LOGGER.error("GStreamer pipeline error: %s (%s)", error.message, debug or "")
        elif message.type == self.Gst.MessageType.WARNING:
            warning, _ = message.parse_warning()
            slot_id = self._slot_for_element(message.src)
            if slot_id and slot_id in self._health and not self._is_prepared_message(message.src, slot_id):
                self._health[slot_id].state = HealthState.degraded
                self._health[slot_id].detail = warning.message
        elif message.type == self.Gst.MessageType.EOS:
            slot_id = self._slot_for_element(message.src)
            if slot_id:
                if self._is_prepared_message(message.src, slot_id):
                    self._mark_prepared_unavailable(slot_id)
                    return
                if self._request_failover(slot_id):
                    return
                self._mark_offline(slot_id, "End of stream")
                self._schedule_reconnect(slot_id)

    def _mark_prepared_unavailable(self, slot_id: str) -> None:
        runtime = self._slots.get(slot_id)
        if runtime and runtime.prepared:
            runtime.prepared.ready = False
            runtime.prepared.last_frame_monotonic = None
            self._restart_prepared(slot_id, runtime.prepared)
            self._schedule_prepared_refresh(slot_id, runtime.prepared)
            if runtime.failover_pending:
                health = self._health.get(slot_id)
                if health:
                    health.state = HealthState.stalled
                    health.detail = "Both rotation feeds unavailable; recovery pending"
                self._arm_rotation_recovery(slot_id)

    def _schedule_prepared_refresh(self, slot_id: str, prepared: _PreparedBranch) -> None:
        runtime = self._slots.get(slot_id)
        if not runtime or runtime.prepared_refresh_source_id:
            return

        def refresh() -> bool:
            current = self._slots.get(slot_id)
            if not current:
                return False
            current.prepared_refresh_source_id = None
            if current.prepared is not prepared:
                return False
            if prepared.ready and prepared.last_frame_monotonic and time.monotonic() - prepared.last_frame_monotonic < 8:
                return False
            if len(current.retired_sources) >= 2:
                now = time.monotonic()
                if now - getattr(current, "retirement_warning_monotonic", 0.0) >= 60:
                    LOGGER.warning("Waiting for retired rotation branches to stop", extra={"slot_id": slot_id})
                    current.retirement_warning_monotonic = now
                health = self._health.get(slot_id)
                # A blocked teardown cannot be repaired by another per-slot
                # retry. Only interrupt the whole wall after this tile has
                # been visibly stalled for two minutes; protect the healthy
                # tiles with a much longer recycle cooldown.
                last_frame = health.last_frame_monotonic if health else None
                stalled_for = now - (last_frame or self._started_at or now)
                if health and health.state == HealthState.stalled and stalled_for >= 120:
                    self._restart_renderer_with_cooldown(
                        slot_id, "stalled rotation with blocked RTSP teardown",
                        allow_healthy_others=True, cooldown_seconds=1800,
                    )
                self._schedule_prepared_refresh(slot_id, prepared)
                return False
            LOGGER.warning("Opening a fresh prepared rotation source", extra={"slot_id": slot_id})
            self._retire_branch(
                current, prepared.source, prepared.queue, prepared.selector_pad,
                prepared.frame_probe_id,
            )
            current.prepared = None
            try:
                self._prepare_stream(slot_id, prepared.spec)
            except Exception:
                LOGGER.exception("Could not open fresh prepared rotation source", extra={"slot_id": slot_id})
            return False

        runtime.prepared_refresh_source_id = self.GLib.timeout_add_seconds(6, refresh)

    def _retire_branch(
        self, runtime: _SlotRuntime, source: Any, queue: Any, selector_pad: Any,
        probe_id: int | None,
    ) -> None:
        """Stop a failed RTSP branch off the main loop, then release its pads."""
        assert self._pipeline is not None
        runtime.retired_sources.append(source)
        runtime.retired_queues.append(queue)

        def stop(element: Any, _: Any) -> None:
            try:
                element.set_state(self.Gst.State.NULL)
                queue.set_state(self.Gst.State.NULL)
            except Exception:
                LOGGER.exception("Could not stop retired camera branch")

            def cleanup() -> bool:
                try:
                    if probe_id is not None:
                        queue.get_static_pad("src").remove_probe(probe_id)
                    queue.get_static_pad("src").unlink(selector_pad)
                    runtime.selector.release_request_pad(selector_pad)
                    self._pipeline.remove(source)
                    self._pipeline.remove(queue)
                except Exception:
                    LOGGER.exception("Could not remove retired camera branch")
                finally:
                    if source in runtime.retired_sources:
                        runtime.retired_sources.remove(source)
                    if queue in runtime.retired_queues:
                        runtime.retired_queues.remove(queue)
                return False

            self.GLib.idle_add(cleanup)

        source.call_async(stop, None)

    def _restart_renderer_with_cooldown(
        self, slot_id: str, reason: str, *,
        allow_healthy_others: bool = False, cooldown_seconds: int = 300,
    ) -> None:
        """Recycle exhausted decoders once, then avoid repeated wall interruptions."""
        healthy_others = sum(
            1 for other_id, health in self._health.items()
            if other_id != slot_id and health.state == HealthState.live
            and health.last_frame_monotonic
            and time.monotonic() - health.last_frame_monotonic < 8
        )
        if healthy_others and not allow_healthy_others:
            LOGGER.debug(
                "Keeping %s other live tiles while %s",
                healthy_others, reason, extra={"slot_id": slot_id},
            )
            return
        marker = Path(os.environ.get("MOSAIVUE_DATA_DIR", "/var/lib/mosaivue")) / "rotation-recovery.stamp"
        now = time.time()
        try:
            last = float(marker.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            last = 0.0
        except OSError:
            LOGGER.exception("Could not read rotation recovery marker", extra={"slot_id": slot_id})
            return
        if now - last < cooldown_seconds:
            LOGGER.debug("Renderer recovery is cooling down", extra={"slot_id": slot_id})
            return
        try:
            marker.write_text(f"{now}\n", encoding="utf-8")
        except OSError:
            LOGGER.exception("Could not write rotation recovery marker", extra={"slot_id": slot_id})
            return
        LOGGER.error("Recycling renderer after %s", reason, extra={"slot_id": slot_id})
        os._exit(75)

    def _restart_prepared(self, slot_id: str, prepared: _PreparedBranch) -> None:
        now = time.monotonic()
        if prepared.restarting or now - prepared.last_restart_monotonic < 5:
            return
        prepared.restarting = True
        prepared.last_restart_monotonic = now

        def stop_source(source: Any, _: Any) -> None:
            try:
                source.set_state(self.Gst.State.NULL)
            except Exception:
                LOGGER.exception("Could not stop failed prepared stream", extra={"slot_id": slot_id})

            def resume() -> bool:
                runtime = self._slots.get(slot_id)
                if runtime and runtime.prepared is prepared:
                    prepared.restarting = False
                    prepared.source.sync_state_with_parent()
                return False

            self.GLib.timeout_add_seconds(1, resume)

        # A blocking RTSP state change on the GLib bus thread stalls every
        # camera. GStreamer runs this reset on a worker thread instead.
        prepared.source.call_async(stop_source, None)

    def _is_prepared_message(self, element: Any, slot_id: str) -> bool:
        runtime = self._slots.get(slot_id)
        prepared = runtime.prepared if runtime else None
        if not prepared:
            return False
        current = element
        while current is not None:
            try:
                if current == prepared.source or current == prepared.queue:
                    return True
                current = current.get_parent()
            except Exception:
                break
        return False

    def _is_retired_message(self, element: Any, slot_id: str) -> bool:
        runtime = self._slots.get(slot_id)
        retired = (*runtime.retired_sources, *runtime.retired_queues) if runtime else ()
        current = element
        while current is not None:
            try:
                if current in retired:
                    return True
                current = current.get_parent()
            except Exception:
                break
        return False

    def _is_placeholder_message(self, element: Any, slot_id: str) -> bool:
        runtime = self._slots.get(slot_id)
        placeholder = runtime.placeholder_source if runtime else None
        current = element
        while current is not None and placeholder is not None:
            try:
                if current == placeholder:
                    return True
                current = current.get_parent()
            except Exception:
                break
        return False

    def _slot_for_element(self, element: Any) -> str | None:
        current = element
        names: list[str] = []
        while current is not None:
            try:
                names.append(current.get_name())
                current = current.get_parent()
            except Exception:
                break
        joined = " ".join(names)
        for slot_id in self._slots:
            if slot_id in joined:
                return slot_id
        return None

    def shutdown(self) -> None:
        if self._loop is None:
            return
        try:
            self._call(self._shutdown)
        finally:
            if self._thread:
                self._thread.join(timeout=10)
            self._thread = None
            self._loop = None

    def _shutdown(self) -> None:
        if self._watchdog_source_id:
            self.GLib.source_remove(self._watchdog_source_id)
            self._watchdog_source_id = None
        if self._pipeline:
            self._pipeline.set_state(self.Gst.State.NULL)
            self._playing = False
            self._slots.clear()
            self._health.clear()
            self._pipeline = None
            self._compositor = None
            self._sink = None
            self._output_scale = None
            self._output_caps = None
        if self._loop:
            self._loop.quit()
