from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class Transport(StrEnum):
    auto = "auto"
    tcp = "tcp"
    udp = "udp"


class LatencyProfile(StrEnum):
    ultra_low = "ultra-low"
    low = "low"
    normal = "normal"
    stable = "stable"


class AspectMode(StrEnum):
    contain = "contain"
    cover = "cover"
    stretch = "stretch"
    native = "native"


class SlotType(StrEnum):
    fixed = "fixed"
    rotation = "rotation"
    manual = "manual"
    empty = "empty"


class StreamProfileIn(BaseModel):
    id: str | None = None
    name: str = Field(default="Main", min_length=1, max_length=100)
    url: str = Field(min_length=7, max_length=4096)
    transport: Transport = Transport.tcp
    codec: str | None = Field(default=None, max_length=32)
    width: int | None = Field(default=None, ge=1, le=16384)
    height: int | None = Field(default=None, ge=1, le=16384)
    fps: float | None = Field(default=None, gt=0, le=240)
    bitrate: int | None = Field(default=None, ge=0)
    latency_profile: LatencyProfile = LatencyProfile.low
    priority: int = Field(default=0, ge=0, le=1000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value.lower().startswith(("rtsp://", "rtsps://")):
            raise ValueError("Only RTSP/RTSPS stream URLs are supported")
        return value


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    vendor: str = Field(default="generic", max_length=100)
    model: str | None = Field(default=None, max_length=255)
    host: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=2048)
    stream_profiles: list[StreamProfileIn] = Field(min_length=1)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return sorted({tag.strip().lower() for tag in value if tag.strip()})


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    vendor: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=255)
    host: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    location: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=2048)
    clear_credentials: bool = False
    stream_profiles: list[StreamProfileIn] | None = None

    @field_validator("tags")
    @classmethod
    def normalize_optional_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return sorted({tag.strip().lower() for tag in value if tag.strip()})


class StreamProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str
    transport: str
    codec: str | None
    width: int | None
    height: int | None
    fps: float | None
    bitrate: int | None
    latency_profile: str
    priority: int


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    enabled: bool
    vendor: str
    model: str | None
    host: str | None
    tags: list[str]
    location: str | None
    username: str | None = None
    has_password: bool = False
    stream_profiles: list[StreamProfileOut]
    created_at: datetime
    updated_at: datetime


Normalized = Annotated[float, Field(ge=0.0, le=1.0)]


class Crop(BaseModel):
    top: Normalized = 0.0
    right: Normalized = 0.0
    bottom: Normalized = 0.0
    left: Normalized = 0.0

    @model_validator(mode="after")
    def check_crop(self) -> "Crop":
        if self.left + self.right >= 1 or self.top + self.bottom >= 1:
            raise ValueError("Crop values must leave a visible area")
        return self


class Slot(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=255)
    type: SlotType = SlotType.fixed
    x: Normalized
    y: Normalized
    width: Annotated[float, Field(gt=0.0, le=1.0)]
    height: Annotated[float, Field(gt=0.0, le=1.0)]
    z_index: int = Field(default=0, ge=-1000, le=1000)
    enabled: bool = True
    camera_id: str | None = None
    rotation_group_id: str | None = None
    selected_camera_id: str | None = None
    stream_profile_id: str | None = None
    stream_selection: Literal["manual", "automatic"] = "automatic"
    aspect_mode: AspectMode = AspectMode.cover
    crop: Crop = Field(default_factory=Crop)
    background: str = "#090d12"
    border: str = "#27313c"
    border_width: int = Field(default=0, ge=0, le=16)
    label: str | None = Field(default=None, max_length=255)
    title_position: Literal["top-left", "top-right", "bottom-left", "bottom-right", "none"] = "bottom-left"
    muted: bool = True
    locked: bool = False
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    pixel_override: dict[str, int] | None = None

    @model_validator(mode="after")
    def validate_geometry_and_source(self) -> "Slot":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("Slot geometry extends beyond the display")
        if self.type == SlotType.fixed and not self.camera_id:
            raise ValueError("Fixed slots require camera_id")
        if self.type == SlotType.rotation and not self.rotation_group_id:
            raise ValueError("Rotation slots require rotation_group_id")
        if self.type == SlotType.manual and not (self.selected_camera_id or self.camera_id):
            raise ValueError("Manual slots require an initial camera")
        return self


class LayoutData(BaseModel):
    schema_version: int = 1
    slots: list[Slot] = Field(default_factory=list, max_length=128)
    background: str = "#05080c"
    output_width: int | None = Field(default=None, ge=320, le=16384)
    output_height: int | None = Field(default=None, ge=240, le=16384)
    grid_columns: int = Field(default=12, ge=1, le=64)
    grid_rows: int = Field(default=12, ge=1, le=64)

    @field_validator("slots")
    @classmethod
    def unique_slot_ids(cls, value: list[Slot]) -> list[Slot]:
        ids = [slot.id for slot in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Slot IDs must be unique")
        return value


class LayoutCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    display_profile_id: str | None = None
    data: LayoutData = Field(default_factory=LayoutData)


class LayoutUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    display_profile_id: str | None = None
    data: LayoutData | None = None
    status: Literal["draft", "active", "archived"] = "draft"


class LayoutRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    revision: int
    status: str
    data: dict[str, Any]
    created_by: str | None
    created_at: datetime


class LayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    current_revision: int
    active: bool
    display_profile_id: str | None
    created_at: datetime
    updated_at: datetime
    revision: LayoutRevisionOut | None = None


class RotationEntry(BaseModel):
    camera_id: str
    weight: int = Field(default=1, ge=1, le=100)
    stream_profile_id: str | None = None


class RotationGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    camera_entries: list[RotationEntry] = Field(min_length=1, max_length=128)
    interval_seconds: int = Field(default=15, ge=2, le=86400)
    order_mode: Literal["sequential", "reverse", "random", "weighted"] = "sequential"
    enabled: bool = True
    preconnect: Literal["off", "next"] = "next"
    failure_behavior: Literal["skip", "hold", "placeholder"] = "skip"
    rotate_together_group: str | None = Field(default=None, max_length=100)
    start_position: int = Field(default=0, ge=0)


class RotationGroupOut(RotationGroupIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class DisplayProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    output_name: str | None = Field(default=None, max_length=100)
    width: int = Field(default=1920, ge=320, le=16384)
    height: int = Field(default=1080, ge=240, le=16384)
    refresh_rate: float = Field(default=60, gt=0, le=240)
    rotation: Literal[0, 90, 180, 270] = 0
    prevent_blanking: bool = True


class DisplayProfileOut(DisplayProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    enabled: bool = True
    layout_id: str
    days: list[int] = Field(default_factory=lambda: list(range(7)))
    start_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    priority: int = Field(default=0, ge=-1000, le=1000)

    @field_validator("days")
    @classmethod
    def valid_days(cls, value: list[int]) -> list[int]:
        if not value or any(day < 0 or day > 6 for day in value):
            raise ValueError("Days must be numbers from 0 (Monday) through 6 (Sunday)")
        return sorted(set(value))


class SetupRequest(BaseModel):
    setup_token: str = Field(min_length=8, max_length=256)
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=1024)
    renderer_backend: Literal["auto", "gstreamer", "omxplayer"] | None = None


class RendererConfigRequest(BaseModel):
    renderer_backend: Literal["auto", "gstreamer", "omxplayer"]


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=1024)


class BackupRequest(BaseModel):
    include_credentials: bool = False
    passphrase: str | None = Field(default=None, min_length=12, max_length=1024)

    @model_validator(mode="after")
    def require_passphrase(self) -> "BackupRequest":
        if self.include_credentials and not self.passphrase:
            raise ValueError("A passphrase is required when including credentials")
        return self


class FocusRequest(BaseModel):
    camera_id: str
    stream_profile_id: str | None = None
    aspect_mode: AspectMode = AspectMode.cover
    duration_seconds: int | None = Field(default=None, ge=1, le=86400)


class ManualSlotRequest(BaseModel):
    camera_id: str
    stream_profile_id: str | None = None


class ImportRequest(BaseModel):
    document: dict[str, Any]
    merge: bool = True
