#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "Run Mosaivue installation with sudo." >&2; exit 1; }

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || true)"
if [[ -f "$SCRIPT_PATH" ]]; then
  SOURCE_ROOT="$(dirname "$SCRIPT_PATH")"
  if [[ -f "$SOURCE_ROOT/pyproject.toml" && -x "$SOURCE_ROOT/installer/install-local.sh" ]]; then
    exec "$SOURCE_ROOT/installer/install-local.sh" "$@"
  fi
fi

command -v curl >/dev/null || { echo "curl is required to download a Mosaivue release." >&2; exit 1; }
if ! command -v python3 >/dev/null; then
  command -v apt-get >/dev/null || { echo "Python 3 is required to read release metadata. Install it and retry." >&2; exit 1; }
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends python3 ca-certificates
fi
command -v sha256sum >/dev/null || { echo "sha256sum is required to verify a release." >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ARCHIVE="${MOSAIVUE_SOURCE_ARCHIVE:-}"
if [[ -z "$ARCHIVE" ]]; then
  RELEASE_API="${MOSAIVUE_RELEASE_API:-https://api.github.com/repos/the-vibe-dev/mosaivue/releases?per_page=20}"
  curl -fsSL "$RELEASE_API" -o "$WORK/releases.json"
  mapfile -t ASSETS < <(python3 - "$WORK/releases.json" <<'PY'
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
    assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
    for name, url in assets.items():
        if re.fullmatch(r"mosaivue-[^-]+-source\.tar\.gz", name) and name + ".sha256" in assets:
            print(url)
            print(assets[name + ".sha256"])
            raise SystemExit(0)
raise SystemExit("No published Mosaivue source archive with SHA-256 checksum was found")
PY
  )
  [[ ${#ASSETS[@]} -eq 2 ]] || { echo "Published Mosaivue release assets are unavailable." >&2; exit 1; }
  ARCHIVE="$WORK/mosaivue-source.tar.gz"
  curl -fsSL "${ASSETS[0]}" -o "$ARCHIVE"
  curl -fsSL "${ASSETS[1]}" -o "$WORK/source.sha256"
  EXPECTED="$(awk '{print $1; exit}' "$WORK/source.sha256")"
  [[ "$EXPECTED" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "Release checksum is malformed." >&2; exit 1; }
  printf '%s  %s\n' "$EXPECTED" "$ARCHIVE" | sha256sum -c -
fi

[[ -f "$ARCHIVE" ]] || { echo "Source archive not found: $ARCHIVE" >&2; exit 1; }
mkdir "$WORK/source"
tar -xzf "$ARCHIVE" -C "$WORK/source" --strip-components=1
[[ -x "$WORK/source/installer/install-local.sh" && -f "$WORK/source/pyproject.toml" ]] || {
  echo "Archive is not a Mosaivue source release." >&2; exit 1;
}
"$WORK/source/installer/install-local.sh" "$@"
