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
