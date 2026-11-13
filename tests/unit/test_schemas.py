from __future__ import annotations

import pytest
from pydantic import ValidationError

from mosaivue.schemas import LayoutData, Slot, StreamProfileIn


def test_stream_profile_only_accepts_rtsp() -> None:
    with pytest.raises(ValidationError):
        StreamProfileIn(name="bad", url="https://example.test/video")


def test_fixed_slot_requires_camera() -> None:
    with pytest.raises(ValidationError):
        Slot(id="a", name="A", type="fixed", x=0, y=0, width=1, height=1)


def test_layout_rejects_duplicate_slot_ids() -> None:
    first = Slot(
        id="same", name="A", type="fixed", camera_id="cam-a", x=0, y=0, width=.5, height=1
    )
    second = Slot(
        id="same", name="B", type="fixed", camera_id="cam-b", x=.5, y=0, width=.5, height=1
    )
    with pytest.raises(ValidationError):
        LayoutData(slots=[first, second])


@pytest.mark.parametrize("url", ["rtsp://", "rtsp:///live", "rtsp://camera:99999/live", "rtsp://camera:notaport/live", "rtsp://camera:0/live", "rtsp://camera/live\n"])
def test_stream_urls_require_valid_host_port_and_no_controls(url):
    from mosaivue.schemas import StreamProfileIn

    with pytest.raises(ValueError):
        StreamProfileIn(url=url)


def test_camera_updates_cannot_remove_all_profiles_or_null_required_fields():
    from mosaivue.schemas import CameraUpdate

    with pytest.raises(ValueError):
        CameraUpdate(stream_profiles=[])
    with pytest.raises(ValueError):
        CameraUpdate(name=None)


@pytest.mark.parametrize("override", [
    {"x": 0, "y": 0},
    {"x": -1, "y": 0, "width": 100, "height": 100},
    {"x": 0, "y": 0, "width": 0, "height": 100},
    {"x": 16000, "y": 0, "width": 1000, "height": 100},
])
def test_pixel_override_shape_and_bounds_are_validated(override):
    from mosaivue.schemas import Slot

    with pytest.raises(ValueError):
        Slot(id="tile", name="Empty", type="empty", x=0, y=0, width=1, height=1, pixel_override=override)


def test_pixel_override_must_fit_explicit_output():
    from mosaivue.schemas import LayoutData, Slot

    slot = Slot(id="tile", name="Empty", type="empty", x=0, y=0, width=1, height=1,
                pixel_override={"x": 500, "y": 0, "width": 500, "height": 100})
    with pytest.raises(ValueError, match="output width"):
        LayoutData(output_width=640, output_height=480, slots=[slot])
    with pytest.raises(ValueError):
        LayoutData(schema_version=2)
