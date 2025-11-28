#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="${STATE_FILE:-${SCRIPT_DIR}/artifacts/vm_state.env}"

if [[ ! -f "${STATE_FILE}" ]]; then
  echo "No VM state file present. Nothing to stop."
  exit 0
fi

# shellcheck disable=SC1090
source "${STATE_FILE}"

if [[ -n "${QEMU_PIDFILE:-}" && -f "${QEMU_PIDFILE}" ]]; then
  if pgrep -F "${QEMU_PIDFILE}" >/dev/null 2>&1; then
    echo "Stopping VM (PID $(cat "${QEMU_PIDFILE}"))"
    kill "$(cat "${QEMU_PIDFILE}")" || true
    sleep 2
    if pgrep -F "${QEMU_PIDFILE}" >/dev/null 2>&1; then
      echo "VM still running; sending SIGKILL"
      kill -9 "$(cat "${QEMU_PIDFILE}")" || true
      sleep 1
    fi
  fi
  rm -f "${QEMU_PIDFILE}"
fi

if [[ -n "${TMPDIR:-}" && -d "${TMPDIR}" ]]; then
  rm -rf "${TMPDIR}"
fi

if [[ -n "${OVERLAY_IMAGE:-}" && -f "${OVERLAY_IMAGE}" ]]; then
  rm -f "${OVERLAY_IMAGE}"
fi

if [[ -n "${SEED_IMAGE:-}" && -f "${SEED_IMAGE}" ]]; then
  rm -f "${SEED_IMAGE}"
fi

rm -f "${STATE_FILE}"

echo "VM stopped and artifacts cleaned up."
