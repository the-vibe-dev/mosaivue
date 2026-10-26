from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .constants import CONFIG_DIR, DATA_DIR, DEFAULT_API_PORT, DEFAULT_BIND


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

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> Settings:
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in allowed})

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.json"
RENDERER_BACKEND_OVERRIDE_PATH = DATA_DIR / "renderer-backend.json"
RENDERER_BACKENDS = {"auto", "gstreamer", "omxplayer"}


def save_renderer_backend(backend: str) -> None:
    if backend not in RENDERER_BACKENDS:
        raise ValueError("Unsupported renderer backend")
    path = RENDERER_BACKEND_OVERRIDE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"renderer_backend": backend}) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640)
    temporary.replace(path)


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("MOSAIVUE_CONFIG", DEFAULT_CONFIG_PATH))
    raw: dict[str, Any] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    settings = Settings.from_mapping(raw)
    try:
        override = json.loads(RENDERER_BACKEND_OVERRIDE_PATH.read_text(encoding="utf-8"))
        selected = override.get("renderer_backend")
        if selected in RENDERER_BACKENDS:
            settings.renderer_backend = selected
    except (OSError, ValueError, AttributeError):
        pass
    env_map: dict[str, tuple[str, Any]] = {
        "MOSAIVUE_BIND": ("bind", str),
        "MOSAIVUE_PORT": ("port", int),
        "MOSAIVUE_RENDERER_BACKEND": ("renderer_backend", str),
        "MOSAIVUE_RENDERER_SINK": ("renderer_sink", str),
        "MOSAIVUE_RTSP_TLS_CA_FILE": ("rtsp_tls_ca_file", str),
        "MOSAIVUE_LOG_LEVEL": ("log_level", str),
        "MOSAIVUE_SECURE_COOKIES": ("secure_cookies", lambda value: value.lower() in {"1", "true", "yes", "on"}),
    }
    for env_name, (attribute, converter) in env_map.items():
        value = os.environ.get(env_name)
        if value is not None:
            setattr(settings, attribute, converter(value))
    return settings


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    path = path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings.to_mapping(), indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640)
    temporary.replace(path)
    return path
