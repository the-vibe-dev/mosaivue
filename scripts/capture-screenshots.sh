#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/docs/images"
python "$ROOT/scripts/capture_screenshots.py" "${MOSAIVUE_SCREENSHOT_URL:-http://127.0.0.1:8080}" "$ROOT/docs/images"
