#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/installer/lib.sh"

for prefix in /opt/mosaivue /srv/cameras /usr/local/mosaivue /var/opt/mosaivue; do
  [[ "$(cw_validate_install_prefix "$prefix")" == "$prefix" ]]
done
for prefix in / /opt /srv /usr /usr/local /usr/local/bin /var /etc/mosaivue /home/user/mosaivue relative '/opt/name with spaces' '/opt/name&sed' '/opt/../../etc' '/opt/name%systemd'; do
  if (cw_validate_install_prefix "$prefix" >/dev/null 2>&1); then
    echo "Unsafe install prefix accepted: $prefix" >&2
    exit 1
  fi
done
[[ "$(cw_validate_install_prefix /opt/mosaivue/)" == /opt/mosaivue ]]

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir "$WORK/shared" "$WORK/config"
touch "$WORK/shared/unrelated"
if (cw_assert_dedicated_prefix "$WORK/shared" >/dev/null 2>&1); then
  echo 'Unrelated nonempty install prefix accepted' >&2; exit 1
fi
cw_assert_dedicated_prefix "$WORK/config"
ln -s /etc/passwd "$WORK/config/config.json"
if (cw_assert_config_entries "$WORK/config" >/dev/null 2>&1); then
  echo 'Symlinked configuration entry accepted' >&2; exit 1
fi
rm "$WORK/config/config.json"
printf 'test' >"$WORK/original"
ln "$WORK/original" "$WORK/config/master.key"
if (cw_assert_config_entries "$WORK/config" >/dev/null 2>&1); then
  echo 'Hardlinked configuration entry accepted' >&2; exit 1
fi
rm "$WORK/config/master.key"
cw_assert_config_entries "$WORK/config"
[[ "$(cw_read_root_metadata "$WORK/missing" fallback)" == fallback ]]
printf '/opt/mosaivue\n' >"$WORK/install-prefix"
chmod 0750 "$WORK"
chmod 0640 "$WORK/install-prefix"
if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  [[ "$(cw_read_root_metadata "$WORK/install-prefix" ignored)" == /opt/mosaivue ]]
  chmod 0770 "$WORK"
  if (cw_read_root_metadata "$WORK/install-prefix" ignored >/dev/null 2>&1); then
    echo 'Group-writable installer directory accepted' >&2; exit 1
  fi
  chmod 0750 "$WORK"
  chmod 0660 "$WORK/install-prefix"
  if (cw_read_root_metadata "$WORK/install-prefix" ignored >/dev/null 2>&1); then
    echo 'Group-writable installer metadata accepted' >&2; exit 1
  fi
else
  if (cw_read_root_metadata "$WORK/install-prefix" ignored >/dev/null 2>&1); then
    echo 'Non-root installer metadata accepted' >&2; exit 1
  fi
fi
rm "$WORK/install-prefix"
ln -s /etc/passwd "$WORK/install-prefix"
if (cw_read_root_metadata "$WORK/install-prefix" ignored >/dev/null 2>&1); then
  echo 'Installer metadata symlink accepted' >&2; exit 1
fi
echo 'Install prefix, ownership, writable-metadata, and symlink checks passed'
