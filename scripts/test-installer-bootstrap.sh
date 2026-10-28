#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -n "$0" "$@"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
cleanup() {
  result=$?
  if [[ "$result" -ne 0 && -f "$WORK/minimal.log" ]]; then cat "$WORK/minimal.log" >&2; fi
  rm -rf "$WORK"
}
trap cleanup EXIT
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

# A minimal Debian image may have curl but no Python until the bootstrap runs.
mkdir "$WORK/minimal-bin"
for tool in readlink dirname curl sha256sum mktemp rm mkdir tar gzip awk; do
  ln -s "$(command -v "$tool")" "$WORK/minimal-bin/$tool"
done
cat >"$WORK/minimal-bin/apt-get" <<'APT'
#!/bin/sh
printf '%s\n' "$*" >>"$MOSAIVUE_TEST_APT_LOG"
if [ "$1" = install ]; then
  /usr/bin/ln -s /usr/bin/python3 "$MOSAIVUE_TEST_BIN/python3"
fi
APT
chmod +x "$WORK/minimal-bin/apt-get"
MOSAIVUE_TEST_BIN="$WORK/minimal-bin" MOSAIVUE_TEST_APT_LOG="$WORK/apt-calls" \
  PATH="$WORK/minimal-bin" /bin/bash "$WORK/install.sh" >"$WORK/minimal.log" 2>&1
[[ -f "$MOSAIVUE_TEST_MARKER" ]]
grep -q '^update$' "$WORK/apt-calls"
grep -q '^install -y --no-install-recommends python3 ca-certificates$' "$WORK/apt-calls"
rm "$MOSAIVUE_TEST_MARKER"

printf 'tamper' >>"$WORK/mosaivue-0.1.0b1-source.tar.gz"
if bash "$WORK/install.sh" >"$WORK/tampered.log" 2>&1; then
  echo "Tampered archive was accepted" >&2
  exit 1
fi
[[ ! -e "$MOSAIVUE_TEST_MARKER" ]]
echo "Bootstrap download, Python prerequisite, checksum, argument forwarding, and tamper rejection passed"
