from types import SimpleNamespace

import pytest

from mosaivue.renderer.base import HealthState, Rect, StreamHealth, StreamSpec
from mosaivue.renderer.gstreamer import GStreamerRenderer


def fallback_renderer():
    renderer = object.__new__(GStreamerRenderer)
    queue = object()
    spec = StreamSpec("tile", "camera", "Camera", "rtsp://192.0.2.1/main", Rect(0, 0, 640, 360), source_width=640, source_height=360)
    runtime = SimpleNamespace(
        source=object(), source_queue=queue, source_codec="h264", spec=spec, prepared=None,
        selector=SimpleNamespace(set_property=lambda *_: None), selector_placeholder_pad=object(),
        placeholder_text=SimpleNamespace(set_property=lambda *_: None),
    )
    renderer._slots = {"tile": runtime}
    renderer._health = {"tile": StreamHealth("tile", "camera", state=HealthState.live, decoder_selected="avdec_h264")}
    renderer._decoder_policy = {"codecs": {"h264": {
        "fixed": "nvh264dec", "rotation": "avdec_h264",
        "candidates": [{"name": "avdec_h264", "kind": "software", "probe": "passed"}],
    }}}
    renderer._software_fallback_slots = {"tile"}
    renderer._persisted_software_fallback_slots = set()
    renderer._software_fallback_pending = {}
    renderer._software_fallback_retry_at = {}
    callbacks = []
    renderer.GLib = SimpleNamespace(idle_add=lambda callback, *args: callbacks.append((callback, args)))
    renderer.Gst = SimpleNamespace(PadProbeReturn=SimpleNamespace(OK="ok"))
    renderer._rotation_software_decode = False
    return renderer, runtime, callbacks


@pytest.mark.parametrize("failure", ["write_error", "not_validated"])
def test_failed_persistence_retries_on_later_frame_without_duplicate_jobs(monkeypatch, failure):
    renderer, runtime, callbacks = fallback_renderer()
    clock = [100.0]
    attempts = []

    def persist(codec, decoder):
        attempts.append((codec, decoder))
        if len(attempts) == 1:
            if failure == "write_error":
                raise OSError("Temporary write failure")
            return False
        return True

    monkeypatch.setattr("mosaivue.renderer.gstreamer.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("mosaivue.renderer.gstreamer.persist_fixed_decoder_fallback", persist)
    renderer._on_frame(None, None, "tile", runtime.source_queue)
    renderer._on_frame(None, None, "tile", runtime.source_queue)
    assert len(callbacks) == 1
    assert not renderer._persisted_software_fallback_slots
    callback, args = callbacks[0]
    assert callback(*args) is False
    assert not renderer._persisted_software_fallback_slots
    clock[0] = 129
    renderer._on_frame(None, None, "tile", runtime.source_queue)
    assert len(callbacks) == 1
    clock[0] = 131
    renderer._on_frame(None, None, "tile", runtime.source_queue)
    callback, args = callbacks[1]
    callback(*args)
    assert attempts == [("h264", "avdec_h264"), ("h264", "avdec_h264")]
    assert renderer._persisted_software_fallback_slots == {"tile"}
    renderer._on_frame(None, None, "tile", runtime.source_queue)
    assert len(callbacks) == 2


@pytest.mark.parametrize("change", ["runtime", "queue", "decoder", "codec"])
def test_queued_verification_cannot_persist_an_obsolete_source(monkeypatch, change):
    renderer, runtime, callbacks = fallback_renderer()
    monkeypatch.setattr("mosaivue.renderer.gstreamer.persist_fixed_decoder_fallback", lambda *_: pytest.fail("Persisted stale frame evidence"))
    renderer._on_frame(None, None, "tile", runtime.source_queue)
    if change == "runtime":
        renderer._slots["tile"] = SimpleNamespace(source_queue=object())
    elif change == "queue":
        runtime.source_queue = object()
    elif change == "decoder":
        renderer._health["tile"].decoder_selected = "nvh264dec"
    else:
        runtime.source_codec = "h265"
    callback, args = callbacks[0]
    assert callback(*args) is False
    assert not renderer._persisted_software_fallback_slots
    assert not renderer._software_fallback_pending


def test_explicit_source_replacement_resets_fallback_and_rejects_old_callback(monkeypatch):
    renderer, runtime, callbacks = fallback_renderer()
    renderer._on_frame(None, None, "tile", runtime.source_queue)
    renderer._persisted_software_fallback_slots.add("tile")
    renderer._software_fallback_retry_at["tile"] = 100
    renderer._cancel_prepared = lambda _: None
    renderer._remove_source_branch = lambda _: None
    renderer._apply_geometry = lambda _: None
    renderer._apply_label = lambda _: None
    renderer._create_source_branch = lambda item: setattr(item, "source_queue", object())
    monkeypatch.setattr("mosaivue.renderer.gstreamer.persist_fixed_decoder_fallback", lambda *_: pytest.fail("Persisted previous camera"))
    replacement = StreamSpec("tile", "new-camera", "New camera", "rtsp://192.0.2.2/main", Rect(0, 0, 640, 360))
    renderer._replace_stream("tile", replacement)
    assert renderer._slots["tile"].spec is replacement
    assert not renderer._software_fallback_slots
    assert not renderer._persisted_software_fallback_slots
    assert not renderer._software_fallback_retry_at
    assert not renderer._software_fallback_pending
    assert runtime.source_codec is None
    callback, args = callbacks[0]
    assert callback(*args) is False


def test_slot_removal_cleans_all_fallback_state(monkeypatch):
    renderer, runtime, callbacks = fallback_renderer()
    renderer._on_frame(None, None, "tile", runtime.source_queue)
    renderer._persisted_software_fallback_slots.add("tile")
    renderer._software_fallback_retry_at["tile"] = 100
    renderer._cancel_prepared = lambda _: None
    renderer._pipeline = None
    renderer._compositor = None
    monkeypatch.setattr("mosaivue.renderer.gstreamer.persist_fixed_decoder_fallback", lambda *_: pytest.fail("Persisted removed camera"))
    renderer._remove_stream("tile")
    assert "tile" not in renderer._slots
    assert not renderer._software_fallback_slots
    assert not renderer._persisted_software_fallback_slots
    assert not renderer._software_fallback_pending
    assert not renderer._software_fallback_retry_at
    callback, args = callbacks[0]
    assert callback(*args) is False


@pytest.mark.parametrize("codec", [None, "h265"])
def test_timeout_does_not_apply_an_unrelated_codec_fallback(codec):
    renderer, runtime, _ = fallback_renderer()
    runtime.source_codec = codec
    renderer._software_fallback_slots.clear()
    renderer._health["tile"].decoder_selected = None
    renderer._try_software_after_first_frame_timeout("tile")
    assert not renderer._software_fallback_slots


def test_rotation_timeout_does_not_change_fixed_decoder_policy():
    renderer, runtime, _ = fallback_renderer()
    runtime.spec.is_rotation = True
    renderer._software_fallback_slots.clear()
    renderer._health["tile"].decoder_selected = "nvh264dec"
    renderer._try_software_after_first_frame_timeout("tile")
    assert not renderer._software_fallback_slots
    assert renderer._decoder_policy["codecs"]["h264"]["fixed"] == "nvh264dec"


def test_codec_observation_ignores_retired_source_callbacks():
    renderer, runtime, _ = fallback_renderer()
    runtime.source_codec = "h265"
    renderer.Gst = SimpleNamespace(ElementFactory=SimpleNamespace(find=lambda *_: True))
    caps = SimpleNamespace(get_size=lambda: 1, get_structure=lambda _: SimpleNamespace(get_name=lambda: "video/x-h264"))
    factory = SimpleNamespace(get_name=lambda: "avdec_h264", get_metadata=lambda _: "Codec/Decoder/Video")
    renderer._select_decoder_factory(None, None, caps, factory, False, "tile", object())
    assert runtime.source_codec == "h265"
    assert renderer._select_decoder_factory(None, None, caps, factory, False, "tile", runtime.source) == 0
    assert runtime.source_codec == "h264"


@pytest.mark.parametrize("sink_name,properties", [
    ("kmssink", {"sync", "force-modesetting"}),
    ("ximagesink", {"sync", "fullscreen", "force-aspect-ratio"}),
])
def test_fullscreen_change_is_guarded_and_preserves_aspect_behavior(sink_name, properties):
    renderer = object.__new__(GStreamerRenderer)
    writes = {}
    sink = SimpleNamespace(
        find_property=lambda name: name in properties,
        set_property=lambda name, value: writes.__setitem__(name, value),
    )
    renderer.Gst = SimpleNamespace(ElementFactory=SimpleNamespace(make=lambda *_: sink))
    assert renderer._make_sink(sink_name) is sink
    assert "fullscreen" not in writes
    assert "force-aspect-ratio" not in writes
