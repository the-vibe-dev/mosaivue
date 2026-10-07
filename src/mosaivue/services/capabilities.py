from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from ..constants import CAPABILITIES_PATH


def _read(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").replace("\x00", "").strip()
    except OSError:
        return None


def _command(command: list[str], timeout: float = 3.0) -> str | None:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def os_release() -> dict[str, str]:
    result: dict[str, str] = {}
    content = _read("/etc/os-release") or ""
    for line in content.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value.strip().strip('"')
    return result


def detect_pi_model() -> str | None:
    model = _read("/proc/device-tree/model")
    if model:
        return model
    cpuinfo = _read("/proc/cpuinfo") or ""
    for line in cpuinfo.splitlines():
        if line.lower().startswith("model") and ":" in line:
            value = line.split(":", 1)[1].strip()
            if "raspberry" in value.lower():
                return value
    return None


def detect_drm_outputs() -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    drm_root = Path("/sys/class/drm")
    if not drm_root.exists():
        return outputs
    for connector in sorted(drm_root.glob("card*-*")):
        status = _read(connector / "status")
        if status not in {"connected", "unknown"}:
            continue
        modes = (_read(connector / "modes") or "").splitlines()
        outputs.append(
            {
                "name": connector.name.split("-", 1)[1] if "-" in connector.name else connector.name,
                "sysfs_name": connector.name,
                "status": status,
                "modes": modes,
                "preferred_mode": modes[0] if modes else None,
            }
        )
    return outputs


def gstreamer_plugins() -> dict[str, bool]:
    plugins = [
        "rtspsrc",
        "rtph264depay",
        "rtph265depay",
        "h264parse",
        "h265parse",
        "v4l2h264dec",
        "v4l2h265dec",
        "omxh264dec",
        "avdec_h264",
        "avdec_h265",
        "compositor",
        "glvideomixer",
        "kmssink",
        "waylandsink",
        "ximagesink",
        "fbdevsink",
        "appsink",
        "jpegenc",
    ]
    if not shutil.which("gst-inspect-1.0"):
        return {name: False for name in plugins}
    result: dict[str, bool] = {}
    for name in plugins:
        try:
            completed = subprocess.run(
                ["gst-inspect-1.0", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
            result[name] = completed.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            result[name] = False
    return result


def cpu_temperature() -> float | None:
    candidates = [
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/sys/class/hwmon/hwmon0/temp1_input"),
    ]
    for path in candidates:
        value = _read(path)
        if value:
            try:
                numeric = float(value)
                return numeric / 1000 if numeric > 500 else numeric
            except ValueError:
                continue
    return None


def detect_capabilities() -> dict[str, Any]:
    release = os_release()
    plugins = gstreamer_plugins()
    pi_model = detect_pi_model()
    memory = psutil.virtual_memory()
    cpu_count = psutil.cpu_count(logical=True) or 1
    architecture = platform.machine()
    decoders = [
        name
        for name in ("v4l2h264dec", "v4l2h265dec", "omxh264dec", "avdec_h264", "avdec_h265")
        if plugins.get(name)
    ]
    sinks = [name for name in ("kmssink", "waylandsink", "ximagesink", "fbdevsink") if plugins.get(name)]
    recommended = "balanced"
    if pi_model and "Raspberry Pi 3" in pi_model:
        recommended = "performance"
    elif pi_model and "Raspberry Pi 5" in pi_model:
        recommended = "quality" if memory.total >= 4 * 1024**3 else "balanced"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "architecture": architecture,
        "platform": platform.platform(),
        "kernel": platform.release(),
        "hostname": platform.node(),
        "os": {
            "id": release.get("ID"),
            "name": release.get("PRETTY_NAME"),
            "version": release.get("VERSION_ID"),
        },
        "pi_model": pi_model,
        "cpu": {
            "logical_count": cpu_count,
            "physical_count": psutil.cpu_count(logical=False),
            "frequency_mhz": getattr(psutil.cpu_freq(), "current", None),
        },
        "memory": {"total_bytes": memory.total, "available_bytes": memory.available},
        "temperature_c": cpu_temperature(),
        "drm_devices": [str(path) for path in sorted(Path("/dev/dri").glob("*"))]
        if Path("/dev/dri").exists()
        else [],
        "displays": detect_drm_outputs(),
        "tools": {
            name: shutil.which(name)
            for name in (
                "gst-launch-1.0",
                "gst-inspect-1.0",
                "gst-discoverer-1.0",
                "ffmpeg",
                "ffprobe",
                "omxplayer",
                "mpv",
                "vlc",
                "modetest",
                "weston-info",
                "xrandr",
            )
        },
        "gstreamer": {
            "version": _command(["gst-launch-1.0", "--version"]),
            "plugins": plugins,
            "decoders": decoders,
            "sinks": sinks,
        },
        "environment": {
            "display": bool(os.environ.get("DISPLAY")),
            "wayland_display": bool(os.environ.get("WAYLAND_DISPLAY")),
            "session_type": os.environ.get("XDG_SESSION_TYPE"),
        },
        "recommended_profile": recommended,
        "recommended_backend": (
            "omxplayer"
            if pi_model and "Raspberry Pi 3" in pi_model
            and shutil.which("omxplayer") and Path("/dev/vchiq").exists()
            else "gstreamer" if plugins.get("compositor") else None
        ),
        "recommended_sink": (
            "kmssink"
            if plugins.get("kmssink") and Path("/dev/dri/card0").exists()
            else "waylandsink"
            if plugins.get("waylandsink") and os.environ.get("WAYLAND_DISPLAY")
            else "ximagesink"
            if plugins.get("ximagesink") and os.environ.get("DISPLAY")
            else "fbdevsink"
            if plugins.get("fbdevsink") and Path("/dev/fb0").exists()
            else None
        ),
    }


def write_capabilities(path: Path = CAPABILITIES_PATH) -> dict[str, Any]:
    report = detect_capabilities()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def live_metrics() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.05),
        "cpu_temperature_c": cpu_temperature(),
        "memory": {
            "percent": memory.percent,
            "used_bytes": memory.used,
            "total_bytes": memory.total,
        },
        "load_average": list(load),
        "boot_time": datetime.fromtimestamp(psutil.boot_time(), tz=UTC).isoformat(),
    }
