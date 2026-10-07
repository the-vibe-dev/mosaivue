from __future__ import annotations

from dataclasses import replace
from typing import Any

from .base import HealthState, Rect, RendererBackend, RendererCapabilities, StreamHealth, StreamSpec


class TestRenderer(RendererBackend):
    """Deterministic in-memory backend. Factory exposes it only when test mode is explicitly enabled."""

    def __init__(self) -> None:
        self.streams: dict[str, StreamSpec] = {}
        self.states: dict[str, StreamHealth] = {}
        self.width = 0
        self.height = 0
        self.running = False

    def initialize(self, *, width: int, height: int, sink: str = "auto") -> None:
        self.width, self.height, self.running = width, height, True

    def capabilities(self) -> RendererCapabilities:
        return RendererCapabilities(
            name="test",
            available=True,
            dynamic_geometry=True,
            dynamic_source_replace=True,
            per_stream_recovery=True,
        )

    def set_output_size(self, width: int, height: int) -> None:
        self.width, self.height = width, height

    def add_stream(self, spec: StreamSpec) -> None:
        self.streams[spec.slot_id] = spec
        self.states[spec.slot_id] = StreamHealth(
            slot_id=spec.slot_id, camera_id=spec.camera_id, state=HealthState.live
        )

    def remove_stream(self, slot_id: str) -> None:
        self.streams.pop(slot_id, None)
        self.states.pop(slot_id, None)

    def replace_stream(self, slot_id: str, spec: StreamSpec) -> None:
        previous = self.streams.get(slot_id)
        health = self.states.get(slot_id)
        self.add_stream(spec)
        if previous and health:
            self.states[slot_id].restart_count = health.restart_count
            self.states[slot_id].switch_count = health.switch_count + int(previous.camera_id != spec.camera_id)
            self.states[slot_id].last_restart_reason = health.last_restart_reason

    def move_stream(self, slot_id: str, rect: Rect) -> None:
        self.streams[slot_id].rect = rect

    def resize_stream(self, slot_id: str, rect: Rect) -> None:
        self.move_stream(slot_id, rect)

    def set_crop_mode(self, slot_id: str, aspect_mode: str, crop: dict[str, float] | None = None) -> None:
        self.streams[slot_id].aspect_mode = aspect_mode
        self.streams[slot_id].crop = crop or {}

    def set_visibility(self, slot_id: str, visible: bool) -> None:
        self.streams[slot_id].opacity = self.streams[slot_id].opacity if visible else 0.0

    def set_opacity(self, slot_id: str, opacity: float) -> None:
        self.streams[slot_id].opacity = opacity

    def set_label(self, slot_id: str, label: str | None, title_position: str) -> None:
        self.streams[slot_id].label = label
        self.streams[slot_id].title_position = title_position

    def set_z_order(self, slot_id: str, z_index: int) -> None:
        self.streams[slot_id].z_index = z_index

    def snapshot(self, slot_id: str | None = None) -> bytes | None:
        return None

    def health(self) -> dict[str, Any]:
        return {
            "backend": "test",
            "state": "RUNNING" if self.running else "STOPPED",
            "output": {"width": self.width, "height": self.height},
            "streams": {key: value.to_dict() for key, value in self.states.items()},
        }

    def restart_stream(self, slot_id: str) -> None:
        self.states[slot_id].restart_count += 1
        self.states[slot_id].last_restart_reason = "Manual restart"
        self.states[slot_id].state = HealthState.live

    def shutdown(self) -> None:
        self.streams.clear()
        self.states.clear()
        self.running = False
