#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -n "$0" "$@"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$ROOT/install.sh" "$WORK/install.sh"

python3 - "$WORK" <<'PY'
from pathlib import Path
import hashlib
import io
import json
import sys
import tarfile

work = Path(sys.argv[1])
name = "mosaivue-0.1.0b1-source.tar.gz"
archive = work / name
with tarfile.open(archive, "w:gz") as tar:
    for path, content, mode in (
        ("mosaivue-0.1.0b1/pyproject.toml", b"[project]\nname='mosaivue'\n", 0o644),
        (
            "mosaivue-0.1.0b1/installer/install-local.sh",
            b"#!/bin/sh\nprintf '%s\\n' \"$*\" >\"$MOSAIVUE_TEST_MARKER\"\n",
            0o755,
        ),
    ):
        entry = tarfile.TarInfo(path)
        entry.size = len(content)
        entry.mode = mode
        tar.addfile(entry, io.BytesIO(content))
sidecar = work / (name + ".sha256")
sidecar.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {name}\n")
(work / "releases.json").write_text(
    json.dumps(
        [
            {
                "draft": False,
                "assets": [
                    {"name": path.name, "browser_download_url": path.as_uri()}
                    for path in (archive, sidecar)
                ],
            }
        ]
    )
)
PY

export MOSAIVUE_RELEASE_API="file://$WORK/releases.json"
export MOSAIVUE_TEST_MARKER="$WORK/invoked"
bash "$WORK/install.sh" --bind 127.0.0.1 >"$WORK/success.log" 2>&1
[[ "$(cat "$MOSAIVUE_TEST_MARKER")" == '--bind 127.0.0.1' ]]
rm "$MOSAIVUE_TEST_MARKER"
printf 'tamper' >>"$WORK/mosaivue-0.1.0b1-source.tar.gz"
if bash "$WORK/install.sh" >"$WORK/tampered.log" 2>&1; then
  echo "Tampered archive was accepted" >&2
  exit 1
fi
[[ ! -e "$MOSAIVUE_TEST_MARKER" ]]
echo "Bootstrap download, checksum, argument forwarding, and tamper rejection passed"
