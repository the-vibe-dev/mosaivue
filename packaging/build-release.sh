#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(awk -F'"' '/^version =/{print $2; exit}' "$ROOT/pyproject.toml")"
OUT="${1:-$ROOT/dist}"; mkdir -p "$OUT"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/mosaivue-$VERSION"
"$ROOT/scripts/copy-release-source.sh" "$TMP/mosaivue-$VERSION"
tar -C "$TMP" -czf "$OUT/mosaivue-$VERSION-source.tar.gz" "mosaivue-$VERSION"
sha256sum "$OUT/mosaivue-$VERSION-source.tar.gz" | awk -v name="mosaivue-$VERSION-source.tar.gz" '{print $1 "  " name}' > "$OUT/mosaivue-$VERSION-source.tar.gz.sha256"
echo "$OUT/mosaivue-$VERSION-source.tar.gz"
