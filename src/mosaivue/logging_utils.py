from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SECRET_KEYS = re.compile(r"password|secret|token|credential|authorization|cookie", re.I)
_RTSP_URL = re.compile(r"(?P<scheme>rtsps?://)(?P<userinfo>[^/@\s]+@)", re.I)
_URL = re.compile(r"\b(?:rtsps?|https?)://[^\s<>\"\']+", re.I)
_SECRET_QUERY = re.compile(r"password|secret|token|credential|authorization|signature|api[_-]?key|access[_-]?key", re.I)


def redact_url(value: str) -> str:
    def sanitized(match: re.Match[str]) -> str:
        url = match.group(0)
        try:
            parts = urlsplit(url)
            hostname = parts.hostname or ""
            if ":" in hostname:
                hostname = f"[{hostname}]"
            if parts.port:
                hostname = f"{hostname}:{parts.port}"
            if parts.username is not None:
                hostname = f"***:***@{hostname}"
            query = urlencode([
                (key, "***" if _SECRET_QUERY.search(key) else item)
                for key, item in parse_qsl(parts.query, keep_blank_values=True)
            ], safe="*")
            return urlunsplit((parts.scheme, hostname, parts.path, query, parts.fragment))
        except ValueError:
            return _RTSP_URL.sub(r"\g<scheme>***:***@", url)
    return _URL.sub(sanitized, value)


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
