#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(awk -F'"' '/^version =/{print $2; exit}' "$ROOT/pyproject.toml")"
ARCH="$(dpkg --print-architecture)"; OUT="${1:-$ROOT/dist}"; STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$OUT" "$STAGE/DEBIAN" "$STAGE/usr/share/mosaivue/source"
"$ROOT/scripts/copy-release-source.sh" "$STAGE/usr/share/mosaivue/source"
cat >"$STAGE/DEBIAN/control" <<CONTROL
Package: mosaivue
Version: $VERSION
Architecture: $ARCH
Maintainer: Mosaivue contributors
Depends: python3 (>= 3.11), python3-venv, python3-pip, python3-dev, python3-gi, python3-gi-cairo, gir1.2-gstreamer-1.0, gir1.2-gst-plugins-base-1.0, gstreamer1.0-tools, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, gstreamer1.0-plugins-bad, gstreamer1.0-plugins-ugly, gstreamer1.0-libav, gstreamer1.0-gl, gstreamer1.0-alsa, ffmpeg, libdrm2, libgl1, build-essential, pkg-config, libffi-dev, libssl-dev, rustc, cargo, curl, ca-certificates, jq, sqlite3, rsync
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
if [ "$1" = configure ]; then
  /usr/share/mosaivue/source/install.sh --non-interactive --skip-packages
fi
POST
cat >"$STAGE/DEBIAN/postrm" <<'POST'
#!/bin/sh
set -e
if [ "$1" = remove ] || [ "$1" = purge ]; then
  if [ -x /opt/mosaivue/current/uninstall.sh ]; then
    /opt/mosaivue/current/uninstall.sh --yes
  fi
fi
POST
chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT/mosaivue_${VERSION}_${ARCH}.deb"
sha256sum "$OUT/mosaivue_${VERSION}_${ARCH}.deb" > "$OUT/mosaivue_${VERSION}_${ARCH}.deb.sha256"
echo "$OUT/mosaivue_${VERSION}_${ARCH}.deb"
