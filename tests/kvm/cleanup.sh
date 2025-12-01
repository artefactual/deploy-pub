#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ":: Removing stale VM artifacts"
find "${SCRIPT_DIR}/.." -maxdepth 2 -type d -name 'artifacts' -print0 | while IFS= read -r -d '' dir; do
  find "${dir}" -mindepth 1 -maxdepth 1 -type d -name 'vm-*' -prune -exec rm -rf {} +
done

echo ":: Removing cached base images (KVM .cache)"
rm -rf "${SCRIPT_DIR}/.cache"

echo ":: Done"
