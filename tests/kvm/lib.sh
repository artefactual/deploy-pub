#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="${STATE_FILE:-${SCRIPT_DIR}/artifacts/vm_state.env}"
REMOTE_SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)
REMOTE_USER=${REMOTE_USER:-ubuntu}
REMOTE_PASSWORD=${REMOTE_PASSWORD:-ubuntu}

load_vm_state() {
  if [[ ! -f "${STATE_FILE}" ]]; then
    echo "VM state file not found at ${STATE_FILE}" >&2
    return 1
  fi

  # shellcheck disable=SC1090
  source "${STATE_FILE}"

  : "${SSH_FORWARD_PORT:?SSH_FORWARD_PORT missing in state file}"
  : "${QEMU_PIDFILE:?QEMU_PIDFILE missing in state file}"
  : "${TMPDIR:?TMPDIR missing in state file}"
  : "${OVERLAY_IMAGE:?OVERLAY_IMAGE missing in state file}"
  : "${SEED_IMAGE:?SEED_IMAGE missing in state file}"
}

remote_ssh() {
  sshpass -p "${REMOTE_PASSWORD}" ssh "${REMOTE_SSH_OPTS[@]}" -p "${SSH_FORWARD_PORT}" "${REMOTE_USER}"@127.0.0.1 "$@"
}

remote_scp() {
  sshpass -p "${REMOTE_PASSWORD}" scp "${REMOTE_SSH_OPTS[@]}" -P "${SSH_FORWARD_PORT}" "$@"
}
