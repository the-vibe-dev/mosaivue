#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$ROOT/installer/lib.sh"
cw_require_root
NON_INTERACTIVE=0; REMOVE_CONFIG=0; REMOVE_DATA=0; REMOVE_LOGS=0; REMOVE_USER=0
PREFIX="$(cat /etc/mosaivue/install-prefix 2>/dev/null || printf '/opt/mosaivue')"
while (($#)); do
  case "$1" in
    --yes) NON_INTERACTIVE=1 ;;
    --purge) NON_INTERACTIVE=1; REMOVE_CONFIG=1; REMOVE_DATA=1; REMOVE_LOGS=1; REMOVE_USER=1 ;;
    --remove-config) REMOVE_CONFIG=1 ;;
    --remove-data) REMOVE_DATA=1 ;;
    --remove-logs) REMOVE_LOGS=1 ;;
    --remove-user) REMOVE_USER=1 ;;
    --prefix) PREFIX="${2:?missing prefix}"; shift ;;
    -h|--help) echo "Usage: sudo ./uninstall.sh [--yes] [--purge] [--remove-config] [--remove-data] [--remove-logs] [--remove-user] [--prefix PATH]"; exit 0 ;;
    *) cw_die "Unknown option: $1" ;;
  esac; shift
done
if [[ "$NON_INTERACTIVE" -eq 0 ]]; then
  echo "Mosaivue application files and services will be removed. Configuration is preserved by default."
  read -r -p "Remove saved configuration and master key? [y/N] " v; [[ "$v" =~ ^[Yy]$ ]] && REMOVE_CONFIG=1
  read -r -p "Remove camera/layout database and backups? [y/N] " v; [[ "$v" =~ ^[Yy]$ ]] && REMOVE_DATA=1
  read -r -p "Remove logs/cache? [y/N] " v; [[ "$v" =~ ^[Yy]$ ]] && REMOVE_LOGS=1
  read -r -p "Remove the mosaivue service account? [y/N] " v; [[ "$v" =~ ^[Yy]$ ]] && REMOVE_USER=1
fi
systemctl disable --now mosaivue-server.service mosaivue-renderer.service 2>/dev/null || true
rm -f /etc/systemd/system/mosaivue-server.service /etc/systemd/system/mosaivue-renderer.service /etc/systemd/system/mosaivue.target
rm -f /usr/lib/tmpfiles.d/mosaivue.conf /usr/local/bin/mosaivue
systemctl daemon-reload
rm -rf "$PREFIX"
[[ "$REMOVE_CONFIG" -eq 1 ]] && rm -rf /etc/mosaivue || cw_log "Preserved /etc/mosaivue"
[[ "$REMOVE_DATA" -eq 1 ]] && rm -rf /var/lib/mosaivue || cw_log "Preserved /var/lib/mosaivue"
[[ "$REMOVE_LOGS" -eq 1 ]] && rm -rf /var/log/mosaivue /var/cache/mosaivue
rm -rf /run/mosaivue
if [[ "$REMOVE_USER" -eq 1 ]]; then userdel mosaivue 2>/dev/null || true; groupdel mosaivue 2>/dev/null || true; fi
cw_log "Mosaivue application removed"
