#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/installer/lib.sh"
cw_require_root
ARCHIVE=""; RELEASE_API="${MOSAIVUE_RELEASE_API:-https://api.github.com/repos/the-vibe-dev/mosaivue/releases?per_page=20}"
PREFIX="$(cat /etc/mosaivue/install-prefix 2>/dev/null || printf '/opt/mosaivue')"
PYTHON_BIN="$(cat /etc/mosaivue/python-bin 2>/dev/null || printf 'python3')"
while (($#)); do
  case "$1" in
    --archive) ARCHIVE="${2:?missing archive}"; shift ;;
    --release-api) RELEASE_API="${2:?missing API}"; shift ;;
    -h|--help) echo "Usage: sudo installer/update.sh [--archive release.tar.gz] [--release-api URL]"; exit 0 ;;
    *) cw_die "Unknown option: $1" ;;
  esac; shift
done
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
if [[ -z "$ARCHIVE" ]]; then
  cw_log "Checking published Mosaivue releases"
  META="$WORK/releases.json"; curl -fsSL "$RELEASE_API" -o "$META"
  mapfile -t URLS < <(python3 - "$META" <<'PY'
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    releases = json.load(stream)
if isinstance(releases, dict):
    releases = [releases]
for release in releases:
    if release.get("draft"):
        continue
    assets = {item["name"]: item["browser_download_url"] for item in release.get("assets", [])}
    for name, url in assets.items():
        if re.fullmatch(r"mosaivue-[^-]+-source\.tar\.gz", name) and name + ".sha256" in assets:
            print(url)
            print(assets[name + ".sha256"])
            raise SystemExit(0)
raise SystemExit("No verified source release found")
PY
  )
  [[ ${#URLS[@]} -eq 2 ]] || cw_die "No verified source release found"
  curl -fsSL "${URLS[0]}" -o "$WORK/release.tar.gz"
  curl -fsSL "${URLS[1]}" -o "$WORK/release.tar.gz.sha256"
  EXPECTED="$(awk '{print $1; exit}' "$WORK/release.tar.gz.sha256")"
  [[ "$EXPECTED" =~ ^[0-9a-fA-F]{64}$ ]] || cw_die "Malformed release checksum"
  printf '%s  %s\n' "$EXPECTED" "$WORK/release.tar.gz" | sha256sum -c -
  ARCHIVE="$WORK/release.tar.gz"
fi
[[ -f "$ARCHIVE" ]] || cw_die "Release archive not found: $ARCHIVE"
mkdir "$WORK/source"; tar -xzf "$ARCHIVE" -C "$WORK/source" --strip-components=1
[[ -x "$WORK/source/installer/install-local.sh" ]] || cw_die "Archive is not a Mosaivue source release"
if ! MOSAIVUE_PYTHON="$PYTHON_BIN" "$WORK/source/installer/install-local.sh" --non-interactive --prefix "$PREFIX"; then
  cw_warn "Update failed; the installer restored the previous release and database snapshot"
  exit 1
fi
cw_log "Update complete; the installer printed the retained release and snapshot paths"
