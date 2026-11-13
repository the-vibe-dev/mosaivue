"""Input and public output for explicit-device ONVIF Media1 onboarding."""
from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


def validate_device_url(value: str) -> str:
    value = value.strip()
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise ValueError("Enter a valid HTTP(S) ONVIF device-service URL") from exc
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or any(character.isspace() or ord(character) < 32 for character in value)
        or (port is not None and port == 0)
    ):
        raise ValueError("Use an HTTP(S) device-service URL without credentials or a fragment")
    return value


class OnvifConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_url: str = Field(min_length=8, max_length=2048)
    username: str = Field(default="", max_length=255)
    password: SecretStr = Field(default=SecretStr(""), max_length=2048)

    _validate_device_url = field_validator("device_url")(validate_device_url)


class OnvifImport(OnvifConnection):
    name: str = Field(min_length=1, max_length=255)
    profile_tokens: list[str] = Field(min_length=1, max_length=32)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Camera name cannot be blank")
        return value.strip()

    @field_validator("profile_tokens")
    @classmethod
    def unique_tokens(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(not v or len(v) > 512 for v in values):
            raise ValueError("Select unique, nonempty ONVIF profile tokens")
        return values


class OnvifProfile(BaseModel):
    token: str
    name: str
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    bitrate: int | None = None


class OnvifProfiles(BaseModel):
    profiles: list[OnvifProfile]
    warnings: list[str] = Field(default_factory=list)
