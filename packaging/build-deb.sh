#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(awk -F'"' '/^version =/{print $2; exit}' "$ROOT/pyproject.toml")"
ARCH="$(dpkg --print-architecture)"; OUT="${1:-$ROOT/dist}"; STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$OUT" "$STAGE/DEBIAN" "$STAGE/opt/mosaivue/releases/$VERSION" "$STAGE/usr/local/bin" "$STAGE/lib/systemd/system" "$STAGE/usr/lib/tmpfiles.d"
"$ROOT/scripts/copy-release-source.sh" "$STAGE/opt/mosaivue/releases/$VERSION"
ln -s "releases/$VERSION" "$STAGE/opt/mosaivue/current"
ln -s /opt/mosaivue/current/.venv/bin/mosaivue "$STAGE/usr/local/bin/mosaivue"
cp "$ROOT/systemd/mosaivue-server.service" "$ROOT/systemd/mosaivue-renderer.service" "$ROOT/systemd/mosaivue.target" "$STAGE/lib/systemd/system/"
cp "$ROOT/systemd/mosaivue.tmpfiles.conf" "$STAGE/usr/lib/tmpfiles.d/mosaivue.conf"
cat >"$STAGE/DEBIAN/control" <<CONTROL
Package: mosaivue
Version: $VERSION
Architecture: $ARCH
Maintainer: Mosaivue contributors
Depends: python3 (>= 3.11), python3-venv, python3-pip, python3-dev, python3-gi, python3-gi-cairo, gir1.2-gstreamer-1.0, gir1.2-gst-plugins-base-1.0, gstreamer1.0-tools, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, gstreamer1.0-plugins-bad, gstreamer1.0-plugins-ugly, gstreamer1.0-libav, gstreamer1.0-gl, gstreamer1.0-alsa, ffmpeg, libdrm2, libgl1, build-essential, pkg-config, curl, ca-certificates, jq, sqlite3, rsync
Section: video
Priority: optional
Homepage: https://github.com/the-vibe-dev/mosaivue
Description: Local-first RTSP camera wall appliance
 Mosaivue manages reusable cameras, responsive layouts, independent rotation
 groups, and a hardware-aware GStreamer HDMI renderer.
CONTROL
cat >"$STAGE/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
if ! getent group mosaivue >/dev/null; then addgroup --system mosaivue; fi
if ! id mosaivue >/dev/null 2>&1; then adduser --system --ingroup mosaivue --home /var/lib/mosaivue --no-create-home --disabled-login mosaivue; fi
adduser mosaivue video >/dev/null 2>&1 || true
adduser mosaivue render >/dev/null 2>&1 || true
systemd-tmpfiles --create /usr/lib/tmpfiles.d/mosaivue.conf || true
REL="$(readlink -f /opt/mosaivue/current)"
"$REL/install.sh" --non-interactive --skip-packages
POST
cat >"$STAGE/DEBIAN/prerm" <<'PRE'
#!/bin/sh
systemctl disable --now mosaivue-server.service mosaivue-renderer.service 2>/dev/null || true
PRE
chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT/mosaivue_${VERSION}_${ARCH}.deb"
sha256sum "$OUT/mosaivue_${VERSION}_${ARCH}.deb" > "$OUT/mosaivue_${VERSION}_${ARCH}.deb.sha256"
echo "$OUT/mosaivue_${VERSION}_${ARCH}.deb"
