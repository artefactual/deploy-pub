#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="${STATE_FILE:-${SCRIPT_DIR}/artifacts/vm_state.env}"

# Helper: stop a qemu process given a pidfile path
stop_pidfile() {
  local pidfile="$1"
  [[ -f "${pidfile}" ]] || return 0
  local pid
  pid="$(cat "${pidfile}" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    echo "Stopping VM (PID ${pid}) from ${pidfile}"
    kill "${pid}" || true
    sleep 2
    if kill -0 "${pid}" 2>/dev/null; then
      echo "VM still running; sending SIGKILL"
      kill -9 "${pid}" || true
      sleep 1
    fi
  fi
  rm -f "${pidfile}"
}

if [[ ! -f "${STATE_FILE}" ]]; then
  echo "No VM state file present at ${STATE_FILE}."
  echo ":: Searching for running VMs (qemu.pid files) under ${SCRIPT_DIR}/.. and ${PWD}"
  mapfile -t PIDFILES < <(find "${SCRIPT_DIR}/.." "${PWD}" -type f -name qemu.pid 2>/dev/null)
  if [[ ${#PIDFILES[@]} -eq 0 ]]; then
    echo "No qemu.pid files found."
    if command -v lsof >/dev/null 2>&1; then
      echo ":: Looking for listening qemu-system-* processes via lsof"
      mapfile -t QPIDS < <(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk '/qemu-system/ {print $2}' | sort -u)
      if [[ ${#QPIDS[@]} -eq 0 ]]; then
        echo "No listening qemu-system processes found. Nothing to stop."
        exit 0
      fi
      for pid in "${QPIDS[@]}"; do
        echo "Stopping qemu PID ${pid} (no pidfile)"
        kill "${pid}" || true
        sleep 2
        kill -9 "${pid}" 2>/dev/null || true
      done
      exit 0
    else
      echo "lsof not available; cannot auto-detect qemu without pidfile."
      exit 1
    fi
  fi
  for pf in "${PIDFILES[@]}"; do
    stop_pidfile "${pf}"
  done
  exit 0
fi

# shellcheck disable=SC1090
source "${STATE_FILE}"

stop_pidfile "${QEMU_PIDFILE:-}"

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
