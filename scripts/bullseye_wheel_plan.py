#!/usr/bin/env python3
"""Select pinned upstream ARMv7 wheels for the actual Bullseye interpreter."""
from __future__ import annotations

import json
import re
import sys
import sysconfig
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "installer/bullseye-wheels.json"


def wheel_plan(version: tuple[int, int], *, implementation: str = "cpython", free_threaded: bool = False) -> list[dict[str, str]]:
    manifest = json.loads(MANIFEST.read_text())
    key = f"{version[0]}.{version[1]}"
    if implementation != "cpython" or free_threaded or key not in manifest["pydantic_core"]:
        raise ValueError(
            "No pinned Bullseye ARMv7 wheel plan for this interpreter; use a supported "
            "standard CPython 3.11-3.15 or the installer's bundled Python 3.11 runtime"
        )
    wheels = [manifest["cryptography"], manifest["pydantic_core"][key]]
    for wheel in wheels:
        url = urlsplit(wheel["url"])
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+\.whl", wheel["filename"])
            or not re.fullmatch(r"[a-f0-9]{64}", wheel["sha256"])
            or url.scheme != "https"
            or url.netloc != "files.pythonhosted.org"
            or Path(url.path).name != wheel["filename"]
            or url.query
            or url.fragment
        ):
            raise ValueError("Invalid pinned Bullseye wheel manifest")
    return wheels


if __name__ == "__main__":
    try:
        selected = wheel_plan(
            sys.version_info[:2], implementation=sys.implementation.name,
            free_threaded=bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(str(error)) from error
    for item in selected:
        print("\t".join(item[key] for key in ("filename", "url", "sha256")))
