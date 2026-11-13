#!/usr/bin/env python3
"""Build a source tree without requiring rsync on development hosts."""
from __future__ import annotations

import fnmatch
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ignored(path: Path, patterns: list[str]) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    candidates = [relative, *(parent.as_posix() for parent in Path(relative).parents if str(parent) != ".")]
    for pattern in patterns:
        pattern = pattern.rstrip("/")
        if "/" in pattern:
            if any(fnmatch.fnmatchcase(candidate, pattern) for candidate in candidates):
                return True
        elif any(fnmatch.fnmatchcase(part, pattern) for part in Path(relative).parts):
            return True
    return False


def copy_source(destination: Path) -> int:
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError("Stage source outside the source tree")
    try:
        top = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        tracked = top.returncode == 0 and Path(top.stdout.strip()).resolve() == ROOT
    except FileNotFoundError:
        tracked = False
    if tracked:
        result = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True)
        paths = [ROOT / value.decode() for value in result.stdout.split(b"\0") if value]
    else:
        patterns = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines() if line.strip() and not line.startswith("#")]
        paths = [path for path in ROOT.rglob("*") if not ignored(path, [".git", *patterns])]
    files = [path for path in paths if path.is_file()]
    for path in files:
        relative = path.relative_to(ROOT)
        forbidden_part = any(
            part in {".pi", ".env", "rollout", ".dev", ".venv", "node_modules"}
            or part.startswith(".env.") for part in relative.parts
        )
        if path.is_symlink() or path.suffix in {".key", ".pem", ".cwbackup", ".db", ".sqlite", ".sqlite3"} or forbidden_part:
            raise ValueError(f"Private or linked runtime artifact in release tree: {relative}")
    destination.mkdir(parents=True, exist_ok=True)
    for path in files:
        target = destination / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return len(files)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: copy_release_source.py DESTINATION")
    try:
        print(f"Staged {copy_source(Path(sys.argv[1]))} source files")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
