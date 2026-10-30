from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "mosaivue"
DEFAULT_API_PORT = 8080
DEFAULT_BIND = "127.0.0.1"


def _path(env: str, default: str) -> Path:
    return Path(os.environ.get(env, default)).expanduser().resolve()


DATA_DIR = _path("MOSAIVUE_DATA_DIR", "/var/lib/mosaivue")
CONFIG_DIR = _path("MOSAIVUE_CONFIG_DIR", "/etc/mosaivue")
CACHE_DIR = _path("MOSAIVUE_CACHE_DIR", "/var/cache/mosaivue")
LOG_DIR = _path("MOSAIVUE_LOG_DIR", "/var/log/mosaivue")
RUN_DIR = _path("MOSAIVUE_RUN_DIR", "/run/mosaivue")
DB_PATH = _path("MOSAIVUE_DB_PATH", str(DATA_DIR / "mosaivue.db"))
MASTER_KEY_PATH = _path("MOSAIVUE_MASTER_KEY_PATH", str(CONFIG_DIR / "master.key"))
SETUP_TOKEN_PATH = _path("MOSAIVUE_SETUP_TOKEN_PATH", str(CONFIG_DIR / "setup-token"))
CAPABILITIES_PATH = _path("MOSAIVUE_CAPABILITIES_PATH", str(DATA_DIR / "capabilities.json"))
DECODER_POLICY_PATH = _path("MOSAIVUE_DECODER_POLICY_PATH", str(DATA_DIR / "decoder-policy.json"))
RENDERER_SOCKET_PATH = _path("MOSAIVUE_RENDERER_SOCKET", str(RUN_DIR / "renderer.sock"))
STATIC_DIR = Path(__file__).resolve().parent / "static"

DEFAULT_SESSION_HOURS = 12
DEFAULT_ROTATION_INTERVAL = 15
MAX_LAYOUT_REVISIONS = 50
