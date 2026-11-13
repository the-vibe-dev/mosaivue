import pytest

from mosaivue.renderer.base import Rect
from mosaivue.renderer.geometry import choose_stream_profile, normalized_to_pixels


def test_normalized_geometry_scales_to_output() -> None:
    rect = normalized_to_pixels(
        {"x": 0.5, "y": 0.25, "width": 0.5, "height": 0.5}, 1920, 1080
    )
    assert rect == Rect(x=960, y=270, width=960, height=540)


def test_pixel_override_wins() -> None:
    rect = normalized_to_pixels(
        {
            "x": 0,
            "y": 0,
            "width": 1,
            "height": 1,
            "pixel_override": {"x": 10, "y": 20, "width": 300, "height": 200},
        },
        1920,
        1080,
    )
    assert rect == Rect(10, 20, 300, 200)


def test_normalized_edge_rounding_keeps_a_visible_pixel() -> None:
    rect = normalized_to_pixels(
        {"x": 0.9999, "y": 0.9999, "width": 0.0001, "height": 0.0001}, 1920, 1080
    )
    assert rect == Rect(1919, 1079, 1, 1)


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"x": 1600, "y": 900, "width": 320, "height": 180}, Rect(639, 359, 1, 1)),
        ({"x": 600, "y": 300, "width": 320, "height": 180}, Rect(600, 300, 40, 60)),
        ({"x": -10, "y": -20, "width": 800, "height": 600}, Rect(0, 0, 640, 360)),
        ({"x": 10, "y": 20, "width": 0, "height": -1}, Rect(10, 20, 1, 1)),
    ],
)
def test_pixel_override_is_clipped_to_current_output(override, expected) -> None:
    assert normalized_to_pixels({"pixel_override": override}, 640, 360) == expected


@pytest.mark.parametrize(("width", "height"), [(0, 1080), (1920, 0), (-1, 1080)])
def test_invalid_output_dimensions_are_rejected(width, height) -> None:
    with pytest.raises(ValueError, match="positive"):
        normalized_to_pixels({"x": 0, "y": 0, "width": 1, "height": 1}, width, height)


def test_automatic_profile_avoids_decoding_4k_for_small_tile() -> None:
    profiles = [
        {"id": "4k", "width": 3840, "height": 2160, "priority": 0},
        {"id": "1080", "width": 1920, "height": 1080, "priority": 1},
        {"id": "low", "width": 640, "height": 360, "priority": 2},
    ]
    selected = choose_stream_profile(profiles, Rect(0, 0, 320, 180))
    assert selected["id"] == "low"
    selected = choose_stream_profile(profiles, Rect(0, 0, 1200, 675))
    assert selected["id"] == "1080"
