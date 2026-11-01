#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/installer/lib.sh"

[[ "$(cw_rotation_normalize_plan off)" == off ]]
[[ "$(cw_rotation_normalize_plan 800x600)" == 800x600 ]]
[[ "$(cw_rotation_normalize_plan auto 800x600)" == 800x600 ]]
if (cw_rotation_normalize_plan 641x360 >/dev/null 2>&1); then
  echo 'Odd rotation dimensions were accepted' >&2
  exit 1
fi
if (cw_rotation_normalize_plan 640x0 >/dev/null 2>&1); then
  echo 'Out-of-range rotation dimensions were accepted' >&2
  exit 1
fi
cw_rockchip_rotation_capable() { return 0; }
[[ "$(cw_rotation_normalize_plan auto)" == 640x360 ]]
cw_rockchip_rotation_capable() { return 1; }
[[ "$(cw_rotation_normalize_plan auto)" == off ]]
echo 'Installer rotation selection passed'
