from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class HealthState(StrEnum):
    connecting = "CONNECTING"
    live = "LIVE"
    degraded = "DEGRADED"
    stalled = "STALLED"
    reconnecting = "RECONNECTING"
    offline = "OFFLINE"
    disabled = "DISABLED"


@dataclass(slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(slots=True)
class StreamSpec:
    slot_id: str
    camera_id: str
    camera_name: str
    url: str
    rect: Rect
    aspect_mode: str = "cover"
    z_index: int = 0
    opacity: float = 1.0
    label: str | None = None
    title_position: str = "bottom-left"
    muted: bool = True
    transport: str = "tcp"
    latency_profile: str = "low"
    stream_profile_id: str | None = None
    source_width: int | None = None
    source_height: int | None = None
    crop: dict[str, float] = field(default_factory=dict)
    is_rotation: bool = False


@dataclass(slots=True)
class StreamHealth:
    slot_id: str
    camera_id: str
    state: HealthState = HealthState.connecting
    detail: str | None = None
    last_frame_monotonic: float | None = None
    restart_count: int = 0
    switch_count: int = 0
    last_restart_reason: str | None = None
    decoded_frames: int = 0
    dropped_frames: int = 0
    reconnect_backoff_seconds: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["state"] = self.state.value
        return result


@dataclass(slots=True)
class RendererCapabilities:
    name: str
    available: bool
    reason: str | None = None
    sinks: list[str] = field(default_factory=list)
    decoders: list[str] = field(default_factory=list)
    dynamic_geometry: bool = False
    dynamic_source_replace: bool = False
    per_stream_recovery: bool = False
    snapshots: bool = False
    hardware_decode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RendererBackend(ABC):
    def start_playback(self) -> None:
        """Start output after the initial layout has linked its streams."""

    def prepare_stream(self, slot_id: str, spec: StreamSpec) -> None:
        """Optionally prepare a replacement while the current stream remains visible."""

    def activate_prepared_stream(self, slot_id: str, spec: StreamSpec) -> None:
        """Use a prepared source when supported, otherwise replace the stream."""
        self.replace_stream(slot_id, spec)

    def cancel_prepared(self, slot_id: str) -> None:
        """Discard a prepared replacement for a slot."""

    @abstractmethod
    def initialize(self, *, width: int, height: int, sink: str = "auto") -> None: ...

    @abstractmethod
    def capabilities(self) -> RendererCapabilities: ...

    @abstractmethod
    def set_output_size(self, width: int, height: int) -> None: ...

    @abstractmethod
    def add_stream(self, spec: StreamSpec) -> None: ...

    @abstractmethod
    def remove_stream(self, slot_id: str) -> None: ...

    @abstractmethod
    def replace_stream(self, slot_id: str, spec: StreamSpec) -> None: ...

    @abstractmethod
    def move_stream(self, slot_id: str, rect: Rect) -> None: ...

    @abstractmethod
    def resize_stream(self, slot_id: str, rect: Rect) -> None: ...

    @abstractmethod
    def set_crop_mode(self, slot_id: str, aspect_mode: str, crop: dict[str, float] | None = None) -> None: ...

    @abstractmethod
    def set_visibility(self, slot_id: str, visible: bool) -> None: ...

    @abstractmethod
    def set_opacity(self, slot_id: str, opacity: float) -> None: ...

    @abstractmethod
    def set_label(self, slot_id: str, label: str | None, title_position: str) -> None: ...

    @abstractmethod
    def set_z_order(self, slot_id: str, z_index: int) -> None: ...

    @abstractmethod
    def snapshot(self, slot_id: str | None = None) -> bytes | None: ...

    @abstractmethod
    def health(self) -> dict[str, Any]: ...

    @abstractmethod
    def restart_stream(self, slot_id: str) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...
