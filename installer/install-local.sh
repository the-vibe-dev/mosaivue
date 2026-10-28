#!/usr/bin/env bash
set -Eeuo pipefail
SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=installer/lib.sh
. "$SOURCE_ROOT/installer/lib.sh"

PREFIX=/opt/mosaivue
NO_START=0
DEV=0
NON_INTERACTIVE=0
BIND_ADDRESS=0.0.0.0
SKIP_PACKAGES=0
PYTHON_BIN="${MOSAIVUE_PYTHON:-python3}"

usage() {
  cat <<USAGE
Usage: sudo ./installer/install-local.sh [options]
  --non-interactive       accept defaults
  --dev                   install editable development copy
  --no-start              install without starting services
  --prefix PATH           release root (default /opt/mosaivue)
  --bind ADDRESS          web bind address (default 0.0.0.0, explicit LAN mode)
  --skip-packages         do not run apt
USAGE
}
while (($#)); do
  case "$1" in
    --non-interactive) NON_INTERACTIVE=1 ;;
    --dev) DEV=1 ;;
    --no-start) NO_START=1 ;;
    --prefix) PREFIX="${2:?missing prefix}"; shift ;;
    --bind) BIND_ADDRESS="${2:?missing bind address}"; shift ;;
    --skip-packages) SKIP_PACKAGES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) cw_die "Unknown option: $1" ;;
  esac
  shift
done

cw_require_root
umask 027
cw_detect_platform
cw_validate_os
VERSION="$(awk -F'"' '/^version =/{print $2; exit}' "$SOURCE_ROOT/pyproject.toml")"
[[ -n "$VERSION" ]] || cw_die "Could not determine version"
RELEASE_DIR="$PREFIX/releases/$VERSION"
PREVIOUS_TARGET="$(readlink -f "$PREFIX/current" 2>/dev/null || true)"
PREVIOUS_RENDERER_ACTIVE=0
PREVIOUS_SERVER_ACTIVE=0
if systemctl is-active --quiet mosaivue-renderer.service; then PREVIOUS_RENDERER_ACTIVE=1; fi
if systemctl is-active --quiet mosaivue-server.service; then PREVIOUS_SERVER_ACTIVE=1; fi
BACKUP_DIR=""
STATE_CHANGES_STARTED=0
CURRENT_CHANGED=0
SERVICES_STOPPED=0

restore_failed_install() {
  local result=$?
  trap - EXIT
  if [[ -n "${RUNTIME_TMP:-}" && -d "$RUNTIME_TMP" ]]; then rm -rf "$RUNTIME_TMP"; fi
  if [[ "$result" -eq 0 ]]; then
    return
  fi
  if [[ "$SERVICES_STOPPED" -eq 1 || "$STATE_CHANGES_STARTED" -eq 1 || "$CURRENT_CHANGED" -eq 1 ]]; then
    cw_warn "Installation failed; restoring the previous appliance state"
    systemctl stop mosaivue-server.service mosaivue-renderer.service 2>/dev/null || true
    if [[ "$CURRENT_CHANGED" -eq 1 ]]; then
      if [[ -n "$PREVIOUS_TARGET" ]]; then
        ln -sfn "$PREVIOUS_TARGET" "$PREFIX/current.rollback"
        mv -Tf "$PREFIX/current.rollback" "$PREFIX/current"
      else
        rm -f "$PREFIX/current"
        systemctl disable mosaivue-server.service mosaivue-renderer.service 2>/dev/null || true
      fi
    fi
    if [[ "$STATE_CHANGES_STARTED" -eq 1 || "$CURRENT_CHANGED" -eq 1 ]]; then
      rm -f /var/lib/mosaivue/mosaivue.db-wal /var/lib/mosaivue/mosaivue.db-shm
      if [[ -f "$BACKUP_DIR/mosaivue.db" ]]; then
        install -o mosaivue -g mosaivue -m 0600 "$BACKUP_DIR/mosaivue.db" /var/lib/mosaivue/mosaivue.db
      else
        rm -f /var/lib/mosaivue/mosaivue.db
      fi
      for item in config.json master.key setup-token install-prefix python-bin; do
        if [[ -f "$BACKUP_DIR/$item" ]]; then
          cp -a "$BACKUP_DIR/$item" "/etc/mosaivue/$item"
        else
          rm -f "/etc/mosaivue/$item"
        fi
      done
      for item in renderer-backend.json capabilities.json; do
        if [[ -f "$BACKUP_DIR/$item" ]]; then
          cp -a "$BACKUP_DIR/$item" "/var/lib/mosaivue/$item"
        else
          rm -f "/var/lib/mosaivue/$item"
        fi
      done
      for entry in \
        /etc/systemd/system/mosaivue-server.service:server.service \
        /etc/systemd/system/mosaivue-renderer.service:renderer.service \
        /etc/systemd/system/mosaivue.target:target \
        /etc/systemd/system/mosaivue-renderer.service.d/rockchip-devices.conf:rockchip-devices.conf \
        /usr/lib/tmpfiles.d/mosaivue.conf:tmpfiles.conf; do
        path="${entry%%:*}"; name="${entry##*:}"
        if [[ -f "$BACKUP_DIR/$name" ]]; then
          cp -a "$BACKUP_DIR/$name" "$path"
        else
          rm -f "$path"
        fi
      done
    fi
    systemctl daemon-reload 2>/dev/null || true
    if [[ "$PREVIOUS_RENDERER_ACTIVE" -eq 1 ]]; then
      systemctl start mosaivue-renderer.service || cw_warn "Could not restart the previous renderer"
    fi
    if [[ "$PREVIOUS_SERVER_ACTIVE" -eq 1 ]]; then
      systemctl start mosaivue-server.service || cw_warn "Could not restart the previous web service"
    fi
  fi
  [[ -n "$BACKUP_DIR" ]] && cw_warn "Pre-install snapshot: $BACKUP_DIR"
  exit "$result"
}
trap restore_failed_install EXIT
# A locally rebuilt beta can have the same package version. Keep the running
# release intact so a failed update can still point current back to it.
if [[ -e "$RELEASE_DIR" ]]; then
  RELEASE_DIR="$PREFIX/releases/$VERSION-$(date -u +%Y%m%dT%H%M%SZ)-$$"
fi

cw_log "Installing Mosaivue $VERSION on $CW_OS_NAME ($CW_ARCH, kernel $CW_KERNEL)"
[[ -n "$CW_PI_MODEL" ]] && cw_log "Detected hardware: $CW_PI_MODEL"
[[ -n "$CW_DRM_CONNECTORS" ]] && cw_log "DRM connectors: $CW_DRM_CONNECTORS"

if [[ "$SKIP_PACKAGES" -eq 0 ]]; then
  export DEBIAN_FRONTEND=noninteractive
  cw_log "Installing operating-system dependencies"
  apt-get update
  apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip python3-dev python3-gi python3-gi-cairo \
    gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    gstreamer1.0-gl gstreamer1.0-x gstreamer1.0-alsa ffmpeg libdrm2 libgl1 \
    build-essential pkg-config libffi-dev libssl-dev rustc cargo curl ca-certificates jq sqlite3 rsync
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 || ! "$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 11)' >/dev/null 2>&1; then
  if [[ "$CW_ARCH" != armhf || "$CW_OS_VERSION" != 11 ]]; then
    cw_die "Python 3.11 or newer is required. Install it, or set MOSAIVUE_PYTHON to its executable."
  fi
  RUNTIME_DIR="$PREFIX/runtime/python-3.11.17"
  if [[ ! -x "$RUNTIME_DIR/bin/python3.11" ]]; then
    cw_log "Installing pinned Python 3.11 runtime for 32-bit Raspberry Pi OS Bullseye"
    RUNTIME_TMP="$(mktemp -d)"
    RUNTIME_ARCHIVE="$RUNTIME_TMP/python.tar.gz"
    curl -fsSL 'https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.11.17%2B20261003-armv7-unknown-linux-gnueabihf-install_only.tar.gz' -o "$RUNTIME_ARCHIVE"
    printf '%s  %s\n' '4c81c1a643631a6c429065a20c2d38962c136361bc3e2e825ba8fe11c3116250' "$RUNTIME_ARCHIVE" | sha256sum -c -
    tar -xzf "$RUNTIME_ARCHIVE" -C "$RUNTIME_TMP"
    install -d -m 0755 "$PREFIX/runtime"
    mv "$RUNTIME_TMP/python" "$RUNTIME_DIR"
    rm -rf "$RUNTIME_TMP"
  fi
  PYTHON_BIN="$RUNTIME_DIR/bin/python3.11"
fi
PYTHON_BIN="$(command -v "$PYTHON_BIN")"
"$PYTHON_BIN" - "$BIND_ADDRESS" <<'PY'
import ipaddress
import sys

try:
    ipaddress.ip_address(sys.argv[1])
except ValueError as exc:
    raise SystemExit(f"Invalid --bind address: {exc}") from exc
PY

if ! getent group mosaivue >/dev/null; then groupadd --system mosaivue; fi
if ! id mosaivue >/dev/null 2>&1; then
  useradd --system --gid mosaivue --home-dir /var/lib/mosaivue --shell /usr/sbin/nologin --comment "Mosaivue camera appliance" mosaivue
fi
for group in video render; do
  getent group "$group" >/dev/null || groupadd --system "$group"
  usermod -a -G "$group" mosaivue
done
install -d -o mosaivue -g mosaivue -m 0750 /var/lib/mosaivue /var/cache/mosaivue /var/log/mosaivue /run/mosaivue
install -d -o root -g mosaivue -m 0770 /etc/mosaivue
install -d -o root -g root -m 0755 "$PREFIX/releases"

cw_log "Staging application release at $RELEASE_DIR"
rm -rf "$RELEASE_DIR.new"
install -d -m 0755 "$RELEASE_DIR.new"
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude 'frontend/node_modules' --exclude 'frontend/dist' \
  --exclude '__pycache__' --exclude '.pytest_cache' --exclude '*.pyc' \
  "$SOURCE_ROOT/" "$RELEASE_DIR.new/"
# rsync -a copies the source root's mode too. curl/update installers unpack
# into private mktemp directories, but the service user must traverse releases.
chmod 0755 "$RELEASE_DIR.new"
"$PYTHON_BIN" -m venv --system-site-packages "$RELEASE_DIR.new/.venv"
"$RELEASE_DIR.new/.venv/bin/python" -m pip install --upgrade pip wheel
if [[ "$CW_ARCH" == armhf && "$CW_OS_VERSION" == 11 ]]; then
  # The piwheels cffi binary targets newer glibc/libffi than Bullseye.
  # Build this small extension against the target image before resolving
  # cryptography; the app install will keep the satisfied version.
  "$RELEASE_DIR.new/.venv/bin/pip" install --no-cache-dir --no-binary=cffi 'cffi==2.1.1'
fi
if [[ "$DEV" -eq 1 ]]; then
  "$RELEASE_DIR.new/.venv/bin/pip" install -e "$RELEASE_DIR.new"
else
  "$RELEASE_DIR.new/.venv/bin/pip" install "$RELEASE_DIR.new"
fi
# The service account needs traversal and read access to this root-built venv.
chmod -R a+rX "$RELEASE_DIR.new/.venv"

if [[ "$PREVIOUS_RENDERER_ACTIVE" -eq 1 || "$PREVIOUS_SERVER_ACTIVE" -eq 1 ]]; then
  SERVICES_STOPPED=1
  cw_log "Stopping the previous services before database migration"
  if [[ "$PREVIOUS_SERVER_ACTIVE" -eq 1 ]]; then systemctl stop mosaivue-server.service; fi
  if [[ "$PREVIOUS_RENDERER_ACTIVE" -eq 1 ]]; then systemctl stop mosaivue-renderer.service; fi
fi
BACKUP_DIR="/var/backups/mosaivue-install-$(date -u +%Y%m%dT%H%M%SZ)-$$"
install -d -m 0700 "$BACKUP_DIR"
printf '%s\n' "$PREVIOUS_TARGET" >"$BACKUP_DIR/previous-release"
chmod 0600 "$BACKUP_DIR/previous-release"
if [[ -f /var/lib/mosaivue/mosaivue.db ]]; then
  "$PYTHON_BIN" - "$BACKUP_DIR/mosaivue.db" <<'PY'
import sqlite3
import sys

source = sqlite3.connect("file:/var/lib/mosaivue/mosaivue.db?mode=ro", uri=True)
destination = sqlite3.connect(sys.argv[1])
try:
    source.backup(destination)
    assert destination.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
finally:
    destination.close()
    source.close()
PY
  chmod 0600 "$BACKUP_DIR/mosaivue.db"
fi
for item in config.json master.key setup-token install-prefix python-bin; do
  [[ ! -f "/etc/mosaivue/$item" ]] || cp -a "/etc/mosaivue/$item" "$BACKUP_DIR/$item"
done
for item in renderer-backend.json capabilities.json; do
  [[ ! -f "/var/lib/mosaivue/$item" ]] || cp -a "/var/lib/mosaivue/$item" "$BACKUP_DIR/$item"
done
for entry in \
  /etc/systemd/system/mosaivue-server.service:server.service \
  /etc/systemd/system/mosaivue-renderer.service:renderer.service \
  /etc/systemd/system/mosaivue.target:target \
  /etc/systemd/system/mosaivue-renderer.service.d/rockchip-devices.conf:rockchip-devices.conf \
  /usr/lib/tmpfiles.d/mosaivue.conf:tmpfiles.conf; do
  path="${entry%%:*}"; name="${entry##*:}"
  [[ ! -f "$path" ]] || cp -a "$path" "$BACKUP_DIR/$name"
done
cw_log "Saved pre-install snapshot at $BACKUP_DIR"
STATE_CHANGES_STARTED=1

if [[ ! -f /etc/mosaivue/config.json ]]; then
  cat >/etc/mosaivue/config.json <<JSON
{
  "bind": "$BIND_ADDRESS",
  "port": 8080,
  "renderer_backend": "auto",
  "renderer_sink": "auto",
  "web_preview_enabled": true,
  "update_checks_enabled": true,
  "session_hours": 12,
  "secure_cookies": false,
  "log_level": "INFO",
  "schedule_enabled": true,
  "profile": "balanced"
}
JSON
fi
chown root:mosaivue /etc/mosaivue/config.json
chmod 0640 /etc/mosaivue/config.json
printf "%s\n" "$PREFIX" >/etc/mosaivue/install-prefix
chown root:mosaivue /etc/mosaivue/install-prefix
chmod 0640 /etc/mosaivue/install-prefix
printf "%s\n" "$PYTHON_BIN" >/etc/mosaivue/python-bin
chown root:mosaivue /etc/mosaivue/python-bin
chmod 0640 /etc/mosaivue/python-bin

export MOSAIVUE_CONFIG=/etc/mosaivue/config.json
export MOSAIVUE_DATA_DIR=/var/lib/mosaivue MOSAIVUE_CONFIG_DIR=/etc/mosaivue MOSAIVUE_CACHE_DIR=/var/cache/mosaivue MOSAIVUE_LOG_DIR=/var/log/mosaivue MOSAIVUE_RUN_DIR=/run/mosaivue
cw_log "Applying transactional database migrations"
( cd "$RELEASE_DIR.new" && ./.venv/bin/alembic -c alembic.ini upgrade head )
cw_log "Initializing master key, setup token, and capability report"
"$RELEASE_DIR.new/.venv/bin/python" - <<'PY'
from mosaivue.security import KeyManager, generate_setup_token
from mosaivue.constants import SETUP_TOKEN_PATH
from mosaivue.db import create_engine
from mosaivue.models import User
from mosaivue.services.capabilities import write_capabilities
from sqlalchemy import func, select
from sqlalchemy.orm import Session
KeyManager().load_or_create()
with Session(create_engine()) as db:
    has_admin = bool(db.scalar(select(func.count()).select_from(User)))
if has_admin:
    SETUP_TOKEN_PATH.unlink(missing_ok=True)
elif not SETUP_TOKEN_PATH.exists():
    print("SETUP_TOKEN=" + generate_setup_token())
try:
    write_capabilities()
except Exception as exc:
    print(f"Capability scan warning: {exc}")
PY
chown -R mosaivue:mosaivue /var/lib/mosaivue /var/cache/mosaivue /var/log/mosaivue
find /var/lib/mosaivue -maxdepth 1 -type f -name 'mosaivue.db*' -exec chmod 0600 {} +
chown root:mosaivue /etc/mosaivue/master.key /etc/mosaivue/setup-token 2>/dev/null || true
chmod 0640 /etc/mosaivue/master.key /etc/mosaivue/setup-token 2>/dev/null || true

rm -rf "$RELEASE_DIR"
mv "$RELEASE_DIR.new" "$RELEASE_DIR"
"$PYTHON_BIN" - "$RELEASE_DIR" <<'PY'
from pathlib import Path
import sys

release = Path(sys.argv[1])
staged = f"{release}.new".encode()
installed = str(release).encode()
for entry in (release / ".venv" / "bin").iterdir():
    if entry.is_symlink() or not entry.is_file():
        continue
    contents = entry.read_bytes()
    if staged in contents:
        entry.write_bytes(contents.replace(staged, installed))
PY
ln -sfn "$RELEASE_DIR" "$PREFIX/current.new"
mv -Tf "$PREFIX/current.new" "$PREFIX/current"
CURRENT_CHANGED=1
ln -sfn "$PREFIX/current/.venv/bin/mosaivue" /usr/local/bin/mosaivue
sed "s|/opt/mosaivue|$PREFIX|g" "$PREFIX/current/systemd/mosaivue-server.service" >/etc/systemd/system/mosaivue-server.service
sed "s|/opt/mosaivue|$PREFIX|g" "$PREFIX/current/systemd/mosaivue-renderer.service" >/etc/systemd/system/mosaivue-renderer.service
install -m 0644 "$PREFIX/current/systemd/mosaivue.target" /etc/systemd/system/mosaivue.target
chmod 0644 /etc/systemd/system/mosaivue-server.service /etc/systemd/system/mosaivue-renderer.service
if [[ -e /dev/mpp_service ]]; then
  install -d -m 0755 /etc/systemd/system/mosaivue-renderer.service.d
  install -m 0644 "$PREFIX/current/systemd/mosaivue-rockchip-devices.conf" \
    /etc/systemd/system/mosaivue-renderer.service.d/rockchip-devices.conf
fi
install -m 0644 "$PREFIX/current/systemd/mosaivue.tmpfiles.conf" /usr/lib/tmpfiles.d/mosaivue.conf
systemd-tmpfiles --create /usr/lib/tmpfiles.d/mosaivue.conf || true
systemctl daemon-reload

if ! "$PREFIX/current/.venv/bin/mosaivue" doctor --json >/var/lib/mosaivue/install-doctor.json 2>/var/log/mosaivue/install-doctor.log; then
  cw_warn "Capability smoke test reported a warning; see /var/log/mosaivue/install-doctor.log"
fi

if [[ "$NO_START" -eq 0 ]]; then
  systemctl enable mosaivue-renderer.service mosaivue-server.service
  # enable --now leaves active units running their old Python environment.
  # Restart after switching current so an update activates the new release.
  # The renderer owns /run/mosaivue through RuntimeDirectory. Start it first
  # so the web service's ReadWritePaths mount exists when its namespace starts.
  systemctl restart mosaivue-renderer.service
  systemctl restart mosaivue-server.service
  HEALTH_HOST="$(jq -r '.bind' /etc/mosaivue/config.json)"
  [[ "$HEALTH_HOST" == 0.0.0.0 || "$HEALTH_HOST" == :: ]] && HEALTH_HOST=127.0.0.1
  [[ "$HEALTH_HOST" == *:* ]] && HEALTH_HOST="[$HEALTH_HOST]"
  HEALTH_PORT="$(jq -r '.port' /etc/mosaivue/config.json)"
  HEALTH_READY=0
  for attempt in $(seq 1 120); do
    if curl -fsS --max-time 2 "http://$HEALTH_HOST:$HEALTH_PORT/healthz" >/dev/null 2>&1; then
      HEALTH_READY=1
      break
    fi
    sleep 1
  done
  [[ "$HEALTH_READY" -eq 1 ]] || cw_die "Web service did not pass /healthz; inspect journalctl -u mosaivue-server"
  systemctl is-active --quiet mosaivue-renderer.service || cw_die "Renderer service is not active"
else
  systemctl enable mosaivue-renderer.service mosaivue-server.service
fi

EFFECTIVE_BIND="$(jq -r '.bind' /etc/mosaivue/config.json)"
EFFECTIVE_PORT="$(jq -r '.port' /etc/mosaivue/config.json)"
case "$EFFECTIVE_BIND" in
  0.0.0.0) SETUP_HOST="$(cw_ipv4)"; [[ -n "$SETUP_HOST" ]] || SETUP_HOST=127.0.0.1 ;;
  ::) SETUP_HOST='[::1]' ;;
  *:*) SETUP_HOST="[$EFFECTIVE_BIND]" ;;
  *) SETUP_HOST="$EFFECTIVE_BIND" ;;
esac
TOKEN="$(cat /etc/mosaivue/setup-token 2>/dev/null || printf 'already-consumed')"
printf '\nMosaivue installed successfully.\n\n'
printf '  Version:      %s\n' "$VERSION"
printf '  Platform:     %s (%s)\n' "$CW_OS_NAME" "$CW_ARCH"
if [[ "$NO_START" -eq 1 ]]; then
  printf '  Web setup (after start): http://%s:%s\n' "$SETUP_HOST" "$EFFECTIVE_PORT"
else
  printf '  Web setup:    http://%s:%s\n' "$SETUP_HOST" "$EFFECTIVE_PORT"
fi
printf '  Setup token:  %s\n' "$TOKEN"
printf '  Terminal UI:  sudo -u mosaivue mosaivue tui\n'
printf '  Diagnostics:  mosaivue doctor\n\n'
printf 'The web service is explicitly bound to %s. Restrict it with a firewall or change /etc/mosaivue/config.json when LAN access is not desired.\n' "$EFFECTIVE_BIND"
if [[ -n "$PREVIOUS_TARGET" && "$PREVIOUS_TARGET" != "$RELEASE_DIR" ]]; then
  printf 'Previous release retained at %s for rollback.\n' "$PREVIOUS_TARGET"
fi
