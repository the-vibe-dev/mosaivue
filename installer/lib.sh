#!/usr/bin/env bash
set -Eeuo pipefail

cw_log() { printf '\033[1;36m[mosaivue]\033[0m %s\n' "$*"; }
cw_warn() { printf '\033[1;33m[mosaivue]\033[0m %s\n' "$*" >&2; }
cw_die() { printf '\033[1;31m[mosaivue]\033[0m %s\n' "$*" >&2; exit 1; }

cw_require_root() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || cw_die "Run this command as root (sudo $0)."
}

cw_detect_platform() {
  CW_ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
  CW_KERNEL="$(uname -r)"
  CW_OS_ID="unknown"; CW_OS_VERSION="unknown"; CW_OS_NAME="Linux"
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    CW_OS_ID="${ID:-unknown}"; CW_OS_VERSION="${VERSION_ID:-unknown}"; CW_OS_NAME="${PRETTY_NAME:-Linux}"
  fi
  CW_PI_MODEL=""
  if [[ -r /proc/device-tree/model ]]; then
    CW_PI_MODEL="$(tr -d '\0' </proc/device-tree/model)"
  fi
  CW_DRM_CONNECTORS="$(find /sys/class/drm -maxdepth 1 -type l -name 'card*-*' -printf '%f ' 2>/dev/null || true)"
}

cw_validate_os() {
  case "$CW_OS_ID" in
    debian|raspbian)
      if ! dpkg --compare-versions "$CW_OS_VERSION" ge 12 && \
         [[ ! ( "$CW_OS_VERSION" == 11 && "$CW_ARCH" == armhf ) ]]; then
        cw_die "Automatic installation requires Debian/Raspberry Pi OS 12 or newer, or 32-bit Raspberry Pi OS 11 for legacy OMXPlayer."
      fi
      ;;
    ubuntu)
      dpkg --compare-versions "$CW_OS_VERSION" ge 24.04 || \
        cw_die "Automatic installation requires Ubuntu 24.04 or newer (Python 3.11+)."
      ;;
    *) cw_die "Unsupported automatic install target: $CW_OS_NAME. Debian, Ubuntu, and Raspberry Pi OS are supported." ;;
  esac
  case "$CW_ARCH" in
    arm64|amd64|armhf|aarch64|x86_64) ;;
    *) cw_die "Unsupported architecture: $CW_ARCH" ;;
  esac
}

cw_ipv4() {
  hostname -I 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i !~ /^127\./ && $i !~ /:/){print $i; exit}}'
}

cw_valid_rotation_size() {
  local value="$1" width height
  [[ "$value" =~ ^([0-9]{1,4})x([0-9]{1,4})$ ]] || return 1
  width=$((10#${BASH_REMATCH[1]}))
  height=$((10#${BASH_REMATCH[2]}))
  ((width >= 160 && width <= 1920 && width % 2 == 0 &&
    height >= 90 && height <= 1080 && height % 2 == 0))
}

cw_rockchip_rotation_capable() {
  [[ -c /dev/mpp_service || -e /dev/mpp_service ]] || return 1
  command -v gst-inspect-1.0 >/dev/null || return 1
  local element
  for element in mppvideodec kmssink videoconvert videoscale videorate capsfilter; do
    gst-inspect-1.0 "$element" >/dev/null 2>&1 || return 1
  done
}

cw_rotation_normalize_plan() {
  local requested="$1" existing="${2:-}"
  case "$requested" in
    off) printf 'off\n' ;;
    auto)
      if [[ -n "$existing" ]] && cw_valid_rotation_size "$existing"; then
        printf '%s\n' "$existing"
      elif cw_rockchip_rotation_capable; then
        printf '640x360\n'
      else
        printf 'off\n'
      fi
      ;;
    *)
      cw_valid_rotation_size "$requested" || cw_die "--rotation-normalize requires auto, off, or even WIDTHxHEIGHT within 160x90–1920x1080"
      printf '%s\n' "$requested"
      ;;
  esac
}
