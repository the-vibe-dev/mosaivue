from __future__ import annotations

from typing import Any

from .base import Rect


def normalized_to_pixels(slot: dict[str, Any], output_width: int, output_height: int) -> Rect:
    if output_width <= 0 or output_height <= 0:
        raise ValueError("Output dimensions must be positive")
    override = slot.get("pixel_override")
    if override:
        x = int(override.get("x", 0))
        y = int(override.get("y", 0))
        width = int(override.get("width", 1))
        height = int(override.get("height", 1))
    else:
        x = round(float(slot["x"]) * output_width)
        y = round(float(slot["y"]) * output_height)
        width = round(float(slot["width"]) * output_width)
        height = round(float(slot["height"]) * output_height)
    # Rounding a tiny edge tile can put its origin exactly at the output size.
    # Pixel overrides also need clipping when a saved layout uses a smaller display.
    x = min(max(0, x), output_width - 1)
    y = min(max(0, y), output_height - 1)
    width = min(max(1, width), output_width - x)
    height = min(max(1, height), output_height - y)
    return Rect(x=x, y=y, width=width, height=height)


def choose_stream_profile(
    profiles: list[dict[str, Any]],
    tile: Rect,
    *,
    mode: str = "automatic",
    preferred_id: str | None = None,
) -> dict[str, Any]:
    if not profiles:
        raise ValueError("Camera has no stream profiles")
    if preferred_id:
        selected = next((item for item in profiles if item.get("id") == preferred_id), None)
        if selected:
            return selected
    ordered = sorted(profiles, key=lambda item: int(item.get("priority", 0)))
    if mode == "manual":
        return ordered[0]
    target_pixels = tile.width * tile.height
    known = [
        item
        for item in ordered
        if isinstance(item.get("width"), int) and isinstance(item.get("height"), int)
    ]
    if not known:
        return ordered[0]
    # Pick the smallest source that is at least 1.15x the tile, otherwise the largest source.
    adequate = [
        item
        for item in known
        if int(item["width"]) * int(item["height"]) >= target_pixels * 1.15
    ]
    if adequate:
        return min(adequate, key=lambda item: int(item["width"]) * int(item["height"]))
    return max(known, key=lambda item: int(item["width"]) * int(item["height"]))
