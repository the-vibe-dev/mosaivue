from __future__ import annotations

import ipaddress
import json
import os
import re
import stat
import tempfile
import warnings
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .constants import CONFIG_DIR, DATA_DIR, DEFAULT_API_PORT, DEFAULT_BIND

RENDERER_BACKENDS = {"auto", "gstreamer", "omxplayer"}
_BOOLEAN_FIELDS = {
    "web_preview_enabled", "update_checks_enabled", "secure_cookies",
    "allow_test_backend", "schedule_enabled",
}
_INTEGER_LIMITS = {
    "port": (1, 65535), "session_hours": (1, 8760),
    "preview_concurrency": (1, 4), "preview_cache_ttl_seconds": (0, 30),
}
_OPTIONAL_TEXT_FIELDS = {"rtsp_tls_ca_file", "output_name", "output_mode", "startup_layout_id"}
_HOSTNAME = re.compile(r"(?=.{1,253}\.?$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.?$")
_ELEMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,127}")


class SettingsError(ValueError):
    """An actionable configuration error that does not echo setting values."""


def _normalize_setting(name: str, value: Any) -> Any:
    if name in _BOOLEAN_FIELDS:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"true", "yes", "on", "1"}:
                return True
            if normalized in {"false", "no", "off", "0"}:
                return False
        raise SettingsError(f"{name} must be a boolean (true/false, yes/no, on/off, or 1/0)")
    if name in _INTEGER_LIMITS:
        if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
            value = int(value)
        minimum, maximum = _INTEGER_LIMITS[name]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise SettingsError(f"{name} must be an integer from {minimum} through {maximum}")
        return value
    if name in _OPTIONAL_TEXT_FIELDS and value is None:
        return None
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SettingsError(f"{name} must be text without control characters")
    value = value.strip()
    if name in _OPTIONAL_TEXT_FIELDS:
        if not value:
            return None
        if len(value) > (4096 if name == "rtsp_tls_ca_file" else 255):
            raise SettingsError(f"{name} exceeds its maximum length")
        if name == "rtsp_tls_ca_file" and not Path(value).is_absolute():
            raise SettingsError("rtsp_tls_ca_file must be an absolute path")
        return value
    if name == "bind":
        try:
            ipaddress.ip_address(value)
        except ValueError:
            labels = value.rstrip(".").split(".")
            valid_labels = all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)
            if not _HOSTNAME.fullmatch(value) or not valid_labels or re.fullmatch(r"[\d.]+", value):
                raise SettingsError("bind must be an IP address or hostname without a URL scheme or port") from None
        return value
    if name == "renderer_backend":
        value = value.casefold()
        if value not in RENDERER_BACKENDS | {"test"}:
            raise SettingsError("renderer_backend must be auto, gstreamer, omxplayer, or the explicitly enabled test backend")
    elif name == "renderer_sink":
        if not _ELEMENT_NAME.fullmatch(value):
            raise SettingsError("renderer_sink must be auto or a GStreamer element name")
    elif name == "log_level":
        value = {"WARN": "WARNING", "FATAL": "CRITICAL"}.get(value.upper(), value.upper())
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"}:
            raise SettingsError("log_level must be DEBUG, INFO, WARNING, ERROR, CRITICAL, or NOTSET")
    elif name == "profile":
        value = value.casefold()
        if value not in {"balanced", "performance", "quality", "low-latency", "custom"}:
            raise SettingsError("profile must be balanced, performance, quality, low-latency, or custom")
    return value


@dataclass(slots=True)
class Settings:
    bind: str = DEFAULT_BIND
    port: int = DEFAULT_API_PORT
    renderer_backend: str = "auto"
    renderer_sink: str = "auto"
    rtsp_tls_ca_file: str | None = None
    output_name: str | None = None
    output_mode: str | None = None
    web_preview_enabled: bool = True
    update_checks_enabled: bool = True
    session_hours: int = 12
    secure_cookies: bool = False
    log_level: str = "INFO"
    allow_test_backend: bool = False
    schedule_enabled: bool = True
    startup_layout_id: str | None = None
    profile: str = "balanced"
    preview_concurrency: int = 1
    preview_cache_ttl_seconds: int = 2

    def __post_init__(self) -> None:
        errors: list[str] = []
        for field in fields(self):
            try:
                setattr(self, field.name, _normalize_setting(field.name, getattr(self, field.name)))
            except SettingsError as exc:
                errors.append(str(exc))
        if errors:
            raise SettingsError("Invalid Mosaivue settings: " + "; ".join(errors))

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> Settings:
        if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
            raise SettingsError("Mosaivue configuration must be a JSON object with text keys")
        allowed = {field.name for field in fields(cls)}
        unknown = set(raw) - allowed
        if unknown:
            warnings.warn(
                "Unknown Mosaivue setting keys ignored: " + ", ".join(sorted(unknown)),
                UserWarning, stacklevel=2,
            )
        # Preserve the historical ability to read configuration containing fields
        # from a newer release, while reporting misspelled/unrecognized keys.
        return cls(**{key: value for key, value in raw.items() if key in allowed})

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.json"
RENDERER_BACKEND_OVERRIDE_PATH = DATA_DIR / "renderer-backend.json"


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = path.lstat()
    except FileNotFoundError:
        previous = None
    if previous is not None and not stat.S_ISREG(previous.st_mode):
        raise SettingsError("Configuration destination must be a regular file")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o640)
            effective_uid = os.geteuid()
            permitted_groups = {os.getegid(), *os.getgroups()}
            target_gid = previous.st_gid if previous is not None else path.parent.stat().st_gid
            # Root CLI writes must remain readable by the service group. A
            # later service-side replacement in its own writable data directory
            # cannot retain a root owner, so keep that writer's UID instead.
            target_uid = previous.st_uid if previous is not None and (
                effective_uid == 0 or previous.st_uid == effective_uid
            ) else -1
            if effective_uid != 0 and target_gid not in permitted_groups:
                target_gid = -1
            os.fchown(handle.fileno(), target_uid, target_gid)
            json.dump(document, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def save_renderer_backend(backend: str) -> None:
    if not isinstance(backend, str) or backend not in RENDERER_BACKENDS:
        raise SettingsError("Unsupported renderer backend")
    _write_json(RENDERER_BACKEND_OVERRIDE_PATH, {"renderer_backend": backend})


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("MOSAIVUE_CONFIG", DEFAULT_CONFIG_PATH))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SettingsError(f"Cannot read valid Mosaivue JSON configuration at {path}") from exc
    if not isinstance(raw, dict):
        raise SettingsError("Mosaivue configuration must be a JSON object")
    try:
        override = json.loads(RENDERER_BACKEND_OVERRIDE_PATH.read_text(encoding="utf-8"))
        selected = override.get("renderer_backend") if isinstance(override, dict) else None
        if isinstance(selected, str) and selected in RENDERER_BACKENDS:
            raw["renderer_backend"] = selected
        else:
            warnings.warn("Ignoring invalid saved renderer-backend override", UserWarning, stacklevel=2)
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError, ValueError):
        warnings.warn("Ignoring unreadable saved renderer-backend override", UserWarning, stacklevel=2)
    env_map = {
        "MOSAIVUE_BIND": "bind", "MOSAIVUE_PORT": "port",
        "MOSAIVUE_RENDERER_BACKEND": "renderer_backend", "MOSAIVUE_RENDERER_SINK": "renderer_sink",
        "MOSAIVUE_RTSP_TLS_CA_FILE": "rtsp_tls_ca_file", "MOSAIVUE_LOG_LEVEL": "log_level",
        "MOSAIVUE_SECURE_COOKIES": "secure_cookies", "MOSAIVUE_SESSION_HOURS": "session_hours",
        "MOSAIVUE_WEB_PREVIEW_ENABLED": "web_preview_enabled",
        "MOSAIVUE_UPDATE_CHECKS_ENABLED": "update_checks_enabled",
        "MOSAIVUE_SCHEDULE_ENABLED": "schedule_enabled",
        "MOSAIVUE_PREVIEW_CONCURRENCY": "preview_concurrency",
        "MOSAIVUE_PREVIEW_CACHE_TTL_SECONDS": "preview_cache_ttl_seconds",
    }
    for env_name, attribute in env_map.items():
        if env_name in os.environ:
            raw[attribute] = os.environ[env_name]
    return Settings.from_mapping(raw)


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    validated = Settings.from_mapping(settings.to_mapping())
    path = path or DEFAULT_CONFIG_PATH
    _write_json(path, validated.to_mapping())
    return path
