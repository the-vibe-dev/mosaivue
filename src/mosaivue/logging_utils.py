from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SECRET_KEYS = re.compile(r"password|secret|token|credential|authorization|cookie", re.I)
_RTSP_URL = re.compile(r"(?P<scheme>rtsps?://)(?P<userinfo>[^/@\s]+@)", re.I)


def redact_url(value: str) -> str:
    if not value.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
        return _RTSP_URL.sub(r"\g<scheme>***:***@", value)
    try:
        parts = urlsplit(value)
        hostname = parts.hostname or ""
        if parts.port:
            hostname = f"{hostname}:{parts.port}"
        if parts.username is not None:
            hostname = f"{parts.username}:***@{hostname}"
        return urlunsplit((parts.scheme, hostname, parts.path, parts.query, parts.fragment))
    except ValueError:
        return _RTSP_URL.sub(r"\g<scheme>***:***@", value)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("***" if _SECRET_KEYS.search(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        value = redact_url(value)
        value = _RTSP_URL.sub(r"\g<scheme>***:***@", value)
        return value
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        for key in ("camera_id", "layout_id", "slot_id", "event"):
            if hasattr(record, key):
                payload[key] = redact(getattr(record, key))
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
