#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MOSAIVUE_DATA_DIR="${MOSAIVUE_DATA_DIR:-$ROOT/.dev/data}"
export MOSAIVUE_CONFIG_DIR="${MOSAIVUE_CONFIG_DIR:-$ROOT/.dev/etc}"
export MOSAIVUE_CACHE_DIR="${MOSAIVUE_CACHE_DIR:-$ROOT/.dev/cache}"
export MOSAIVUE_LOG_DIR="${MOSAIVUE_LOG_DIR:-$ROOT/.dev/log}"
export MOSAIVUE_RUN_DIR="${MOSAIVUE_RUN_DIR:-$ROOT/.dev/run}"
export MOSAIVUE_DB_PATH="$MOSAIVUE_DATA_DIR/mosaivue.db"
export MOSAIVUE_MASTER_KEY_PATH="$MOSAIVUE_CONFIG_DIR/master.key"
export MOSAIVUE_SETUP_TOKEN_PATH="$MOSAIVUE_CONFIG_DIR/setup-token"
export MOSAIVUE_RENDERER_SOCKET="$MOSAIVUE_RUN_DIR/renderer.sock"
mkdir -p "$MOSAIVUE_DATA_DIR" "$MOSAIVUE_CONFIG_DIR" "$MOSAIVUE_CACHE_DIR" "$MOSAIVUE_LOG_DIR" "$MOSAIVUE_RUN_DIR"
cd "$ROOT"
exec env PYTHONPATH=src python -m mosaivue.api.app
