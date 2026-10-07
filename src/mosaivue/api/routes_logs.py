from __future__ import annotations

import re
import subprocess
from datetime import datetime

from fastapi import APIRouter, Query

from ..logging_utils import redact
from .dependencies import Auth

router = APIRouter(prefix="/logs", tags=["logs"])
_SAFE_SINCE = re.compile(r"^(?:\d+[smhdw]|today|yesterday|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)$")


@router.get("")
def logs(
    _: Auth,
    since: str = Query(default="1h", max_length=32),
    camera: str | None = Query(default=None, max_length=100),
    renderer: bool = False,
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, object]:
    if not _SAFE_SINCE.match(since):
        since = "1h"
    units = ["mosaivue-renderer.service"] if renderer else ["mosaivue-server.service", "mosaivue-renderer.service"]
    command = ["journalctl", "--no-pager", "--since", since, "-n", str(limit), "-o", "json"]
    for unit in units:
        command.extend(["-u", unit])
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        entries: list[dict[str, object]] = []
        import json

        for line in completed.stdout.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = str(redact(item.get("MESSAGE", "")))
            if camera and camera.casefold() not in message.casefold():
                continue
            timestamp = item.get("__REALTIME_TIMESTAMP")
            if timestamp:
                try:
                    timestamp = datetime.fromtimestamp(int(timestamp) / 1_000_000).isoformat()
                except (ValueError, TypeError):
                    pass
            entries.append(
                {
                    "timestamp": timestamp,
                    "unit": item.get("_SYSTEMD_UNIT"),
                    "priority": item.get("PRIORITY"),
                    "message": message,
                }
            )
        return {"entries": entries, "source": "journald", "error": completed.stderr.strip() or None}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"entries": [], "source": "unavailable", "error": str(exc)}
