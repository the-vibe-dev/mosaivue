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


def renderer_status(cli: str = "/usr/local/bin/mosaivue") -> dict[str, object]:
    args = [cli, "status", "--json"]
    if os.geteuid() == 0 and shutil.which("runuser"):
        args = ["runuser", "-u", "mosaivue", "--", *args]
    result = command(*args, timeout=45)
    if result is None or result.returncode != 0:
        return {"error": "status command unavailable"}
    try:
        response = json.loads(result.stdout)
        raw = response["renderer"]
        if not isinstance(raw, dict) or not isinstance(raw.get("streams", {}), dict):
            raise ValueError("invalid renderer state")
    except (ValueError, KeyError, TypeError):
        return {"error": "invalid status response"}
    streams = {
        slot_id: {
            "camera_id": stream.get("camera_id"),
            "state": stream.get("state"),
            "frames": stream.get("decoded_frames"),
            "cuts": stream.get("switch_count"),
            "restarts": stream.get("restart_count"),
            "decoder": stream.get("decoder_selected"),
            "last_frame_age_seconds": round(max(0.0, time.monotonic() - last), 1)
            if isinstance((last := stream.get("last_frame_monotonic")), (int, float))
            else None,
        }
        for slot_id, stream in raw.get("streams", {}).items() if isinstance(stream, dict)
    }
    return {
        "state": raw.get("state"),
        "version": response.get("version"),
        "active_layout_id": raw.get("active_layout_id"),
        "active_revision": raw.get("active_revision"),
        "active_revision_id": raw.get("active_revision_id"),
        "backend": raw.get("backend"),
        "sink": raw.get("sink"),
        "rotation_normalize_caps": raw.get("rotation_normalize_caps"),
        "rotation_input_caps": raw.get("rotation_input_caps"),
        "uptime_seconds": raw.get("uptime_seconds"),
        "live": sum(stream["state"] == "LIVE" for stream in streams.values()),
        "total": len(streams),
        "rotation_cuts": max((stream["cuts"] or 0 for stream in streams.values()), default=0),
        "total_frames": sum(stream["frames"] or 0 for stream in streams.values()),
        "streams": streams,
    }


def web_healthy(url: str = "http://127.0.0.1:8080/healthz") -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=3) as response:
            payload = json.loads(response.read(4097))
            return response.status == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
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
    lines = result.stdout.splitlines()
    if not lines:
        return {"state": "unavailable"}
    values = [value.strip() for value in lines[0].split(",")]
    names = ("gpu_percent", "decoder_percent", "memory_mib")
    return {name: values[index] for index, name in enumerate(names) if index < len(values)}


def sample(
    *, cli: str = "/usr/local/bin/mosaivue", health_url: str = "http://127.0.0.1:8080/healthz",
    run_id: str | None = None, source_id: str | None = None,
) -> dict[str, object]:
    connectors = {}
    for path in sorted(Path("/sys/class/drm").glob("card*-*")):
        status = path / "status"
        if status.is_file():
            connectors[path.name] = status.read_text(encoding="utf-8").strip()
    return {
        "time_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 (Python 3.9 on Pi 3)
        "schema_version": 2,
        "host": socket.gethostname(),
        "run_id": run_id,
        "source_id": source_id,
        "renderer_service": service("mosaivue-renderer.service"),
        "web_service": service("mosaivue-server.service"),
        "xorg_service": service("mosaivue-xorg.service"),
        "web_healthy": web_healthy(health_url),
        "renderer": renderer_status(cli),
        "gpu": gpu_status(),
        "connectors": connectors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/var/log/mosaivue/overnight-health.jsonl"))
    parser.add_argument("--cli", default="/usr/local/bin/mosaivue", help="Installed CLI symlink or explicit path")
    parser.add_argument("--health-url", default="http://127.0.0.1:8080/healthz", help="Local health URL; use http://[::1]:PORT/healthz for IPv6")
    parser.add_argument("--run-id", help="New label after each deployment/reboot being qualified")
    parser.add_argument("--source-id", help="Exact deployed source archive SHA256 or commit; operator supplied")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(sample(cli=args.cli, health_url=args.health_url, run_id=args.run_id, source_id=args.source_id), separators=(",", ":")) + "\n")
    os.chmod(args.output, 0o640)


if __name__ == "__main__":
    main()
