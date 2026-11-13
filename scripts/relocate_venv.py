#!/usr/bin/env python3
"""Relocate entry points and editable metadata after staging a release."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def relocate_venv(release: Path) -> int:
    release = release.absolute()
    staged = f"{release}.new".encode()
    installed = str(release).encode()
    pattern = re.compile(re.escape(staged) + rb"(?=/|$|[\r\n\"'])")
    venv = release / ".venv"
    candidates = list((venv / "bin").iterdir())
    for directory in (venv / "lib").glob("python*/site-packages"):
        candidates.extend(directory.glob("*.pth"))
        candidates.extend(directory.glob("*.dist-info/direct_url.json"))
    count = 0
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            continue
        contents = path.read_bytes()
        if b"\x00" in contents:
            continue
        updated = pattern.sub(lambda _: installed, contents)
        if updated != contents:
            path.write_bytes(updated)
            count += 1
    return count


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: relocate_venv.py INSTALLED_RELEASE_DIRECTORY")
    print(f"Relocated {relocate_venv(Path(sys.argv[1]))} environment paths")
