#!/usr/bin/env python3
"""Append a credential-free appliance health sample for beta soak tests."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def command(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def service(name: str) -> dict[str, str]:
    result = command(
        "systemctl", "show", name,
        "--property=ActiveState,NRestarts,MainPID,ExecMainStartTimestamp",
        "--no-pager", timeout=5,
    )
    if result is None or result.returncode != 0:
        return {"state": "unknown"}
    properties = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return {
        "state": properties.get("ActiveState", "unknown"),
        "restarts": properties.get("NRestarts", "unknown"),
        "pid": properties.get("MainPID", "unknown"),
        "started": properties.get("ExecMainStartTimestamp", "unknown"),
    }


def renderer_status() -> dict[str, object]:
    cli = "/opt/mosaivue/current/.venv/bin/mosaivue"
    args = [cli, "status", "--json"]
    if os.geteuid() == 0 and shutil.which("runuser"):
        args = ["runuser", "-u", "mosaivue", "--", *args]
    result = command(*args, timeout=45)
    if result is None or result.returncode != 0:
        return {"error": "status command unavailable"}
    try:
        raw = json.loads(result.stdout)["renderer"]
    except (ValueError, KeyError, TypeError):
        return {"error": "invalid status response"}
    streams = {
        slot_id: {
            "state": stream.get("state"),
            "frames": stream.get("decoded_frames"),
            "cuts": stream.get("switch_count"),
            "restarts": stream.get("restart_count"),
            "decoder": stream.get("decoder_selected"),
            "last_frame_age_seconds": round(max(0.0, time.monotonic() - last), 1)
            if isinstance((last := stream.get("last_frame_monotonic")), (int, float))
            else None,
        }
        for slot_id, stream in raw.get("streams", {}).items()
    }
    return {
        "state": raw.get("state"),
        "backend": raw.get("backend"),
        "sink": raw.get("sink"),
        "uptime_seconds": raw.get("uptime_seconds"),
        "live": sum(stream["state"] == "LIVE" for stream in streams.values()),
        "total": len(streams),
        "rotation_cuts": max((stream["cuts"] or 0 for stream in streams.values()), default=0),
        "total_frames": sum(stream["frames"] or 0 for stream in streams.values()),
        "streams": streams,
    }


def web_healthy() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/healthz", timeout=3) as response:
            return response.status == 200 and json.load(response).get("status") == "ok"
    except (OSError, ValueError):
        return False


def gpu_status() -> dict[str, str] | None:
    if not shutil.which("nvidia-smi"):
        return None
    result = command(
        "nvidia-smi", "--query-gpu=utilization.gpu,utilization.decoder,memory.used",
        "--format=csv,noheader,nounits", timeout=5,
    )
    if result is None or result.returncode != 0:
        return {"state": "unavailable"}
    values = [value.strip() for value in result.stdout.splitlines()[0].split(",")]
    names = ("gpu_percent", "decoder_percent", "memory_mib")
    return {name: values[index] for index, name in enumerate(names) if index < len(values)}


def sample() -> dict[str, object]:
    connectors = {}
    for path in sorted(Path("/sys/class/drm").glob("card*-*")):
        status = path / "status"
        if status.is_file():
            connectors[path.name] = status.read_text(encoding="utf-8").strip()
    return {
        "time_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 (Python 3.9 on Pi 3)
        "host": socket.gethostname(),
        "renderer_service": service("mosaivue-renderer.service"),
        "web_service": service("mosaivue-server.service"),
        "xorg_service": service("mosaivue-xorg.service"),
        "web_healthy": web_healthy(),
        "renderer": renderer_status(),
        "gpu": gpu_status(),
        "connectors": connectors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/var/log/mosaivue/overnight-health.jsonl"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(sample(), separators=(",", ":")) + "\n")
    os.chmod(args.output, 0o640)


if __name__ == "__main__":
    main()
