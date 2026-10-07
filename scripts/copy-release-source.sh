#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:?destination required}"
mkdir -p "$DEST"

if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  && [[ "$(git -C "$ROOT" rev-parse --show-toplevel)" == "$ROOT" ]]; then
  # Copy the checked-in file set from the working tree, including freshly
  # rebuilt static assets, without admitting unrelated local files.
  git -C "$ROOT" ls-files -z | rsync -a --from0 --files-from=- "$ROOT/" "$DEST/"
else
  # Source archives do not contain .git; use the same local-artifact exclusions.
  rsync -a --exclude '.git/' --exclude-from "$ROOT/.gitignore" "$ROOT/" "$DEST/"
fi

if [[ -e "$DEST/.pi" || -e "$DEST/.env" || -e "$DEST/rollout" ]]; then
  echo "Private runtime artifact entered release source" >&2
  exit 1
fi
if find "$DEST" -type f \( -name '*.key' -o -name '*.pem' -o -name '*.cwbackup' -o -name '*.db' \) -print -quit | grep -q .; then
  echo "Credential or database file entered release source" >&2
  exit 1
fi
