#!/usr/bin/env bash
set -euo pipefail

SUITE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SUITE_DIR}/../.." && pwd)"
KVM_DIR="${PROJECT_ROOT}/tests/kvm"
STATE_FILE="${STATE_FILE:-${SUITE_DIR}/artifacts/dip_upload_vm.env}"
REQUIREMENTS_FILE="${SUITE_DIR}/requirements.yml"

export STATE_FILE
export VM_NAME="${VM_NAME:-archivematica-dip-upload}"
export SSH_FORWARD_PORT="${SSH_FORWARD_PORT:-2222}"
export FORWARD_PORTS="${FORWARD_PORTS:-"2222:22 8000:80 8001:8000 9000:9000"}"

SKIP_CLEANUP=${SKIP_CLEANUP:-0}

galaxy_retry() {
  local cmd="$1"
  local retries=${2:-5}
  local delay=${3:-10}
  local attempt=1
  while true; do
    if eval "$cmd"; then
      return 0
    fi
    if [[ $attempt -ge $retries ]]; then
      echo "Command failed after ${attempt} attempts: $cmd" >&2
      return 1
    fi
    echo "Retrying in ${delay}s... (${attempt}/${retries})"
    sleep "$delay"
    attempt=$((attempt + 1))
  done
}

cleanup() {
  if [[ "${SKIP_CLEANUP}" -eq 1 ]]; then
    if [[ -n "${QEMU_PIDFILE:-}" && -f "${QEMU_PIDFILE}" ]]; then
      echo ":: Leaving VM running for debugging (PID $(cat "${QEMU_PIDFILE}"))"
    fi
    return
  fi
  STATE_FILE="${STATE_FILE}" "${KVM_DIR}/stop_vm.sh" || true
}
trap cleanup EXIT

echo ":: Starting KVM guest"
"${KVM_DIR}/start_vm.sh"

source "${KVM_DIR}/lib.sh"
load_vm_state

SCRIPT_DIR="${SUITE_DIR}"
cd "${SCRIPT_DIR}"
echo ":: Working dir ${PWD}"
echo ":: Using requirements ${REQUIREMENTS_FILE}"
export ANSIBLE_ROLES_PATH="${SCRIPT_DIR}/roles:${HOME}/.ansible/roles"

echo ":: Installing Ansible Galaxy roles"
galaxy_retry "ansible-galaxy role install -r '${REQUIREMENTS_FILE}'" "${GALAXY_RETRIES:-5}" "${GALAXY_DELAY:-10}"

if [[ "${SKIP_COLLECTIONS:-1}" -ne 1 ]]; then
  echo ":: Installing Ansible Galaxy collections"
  if [[ -f "${SUITE_DIR}/collections.yml" ]]; then
    galaxy_retry "ansible-galaxy collection install -r '${SUITE_DIR}/collections.yml'" "${GALAXY_RETRIES:-5}" "${GALAXY_DELAY:-10}"
  else
    echo ":: No collections.yml found; skipping collections install."
  fi
else
  echo ":: Skipping Galaxy collections install (set SKIP_COLLECTIONS=0 to enable)"
fi

echo ":: Running Archivematica and AtoM playbooks"
ANSIBLE_FORCE_COLOR=1 ANSIBLE_STDOUT_CALLBACK=debug ansible-playbook \
  -i "${SCRIPT_DIR}/inventory.ini" \
  -u ubuntu \
  "$@" \
  "${SCRIPT_DIR}/archivematica.yml"

ANSIBLE_FORCE_COLOR=1 ANSIBLE_STDOUT_CALLBACK=debug ansible-playbook \
  -i "${SCRIPT_DIR}/inventory.ini" \
  -u ubuntu \
  "$@" \
  "${SCRIPT_DIR}/atom.yml"
