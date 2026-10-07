from __future__ import annotations

import os
import signal
import subprocess
from typing import Any

from ..config import RENDERER_BACKENDS, load_settings, save_renderer_backend
from ..renderer.factory import available_backends


def renderer_options() -> list[dict[str, Any]]:
    detected = available_backends(load_settings())
    production = [item for item in detected if item.get("name") in {"gstreamer", "omxplayer"}]
    return [
        {"name": "auto", "available": any(item.get("available") for item in production), "reason": None},
        *production,
    ]


def renderer_config() -> dict[str, Any]:
    return {"selected": load_settings().renderer_backend, "options": renderer_options()}


def select_renderer_backend(backend: str) -> bool:
    if backend not in RENDERER_BACKENDS:
        raise ValueError("Unsupported renderer backend")
    option = next((item for item in renderer_options() if item["name"] == backend), None)
    if option is None or not option["available"]:
        raise ValueError(f"Renderer backend {backend} is unavailable on this device")
    changed = load_settings().renderer_backend != backend
    save_renderer_backend(backend)
    return changed


def request_renderer_restart() -> bool:
    if os.environ.get("MOSAIVUE_TESTING") == "1":
        return False
    try:
        result = subprocess.run(
            ["systemctl", "show", "--property=MainPID", "--value", "mosaivue-renderer.service"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if result.returncode:
            return False
        pid = int(result.stdout.strip())
        if pid < 2:
            return False
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
