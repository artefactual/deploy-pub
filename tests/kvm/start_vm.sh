#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

STATE_FILE="${STATE_FILE:-${SCRIPT_DIR}/artifacts/vm_state.env}"
ARTIFACTS_DIR="$(dirname "${STATE_FILE}")"
CACHE_DIR="${CACHE_DIR:-${SCRIPT_DIR}/.cache}"
IMAGE_URL="${IMAGE_URL:-https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img}"
IMAGE_MIRRORS=(${IMAGE_MIRRORS:-})
IMAGE_PATH="${IMAGE_PATH:-${CACHE_DIR}/$(basename "${IMAGE_URL}")}"
VM_NAME="${VM_NAME:-am-test}"
VM_CPUS="${VM_CPUS:-4}"
VM_MEMORY_MB="${VM_MEMORY_MB:-8192}"
DISK_SIZE_GB="${DISK_SIZE_GB:-15}"
SSH_FORWARD_PORT="${SSH_FORWARD_PORT:-2222}"
# Space-separated list of host:guest TCP forwards, e.g. "2222:22 8000:80 8001:8000 9000:9000"
FORWARD_PORTS="${FORWARD_PORTS:-"2222:22 8000:80 8001:8000"}"
DISABLE_IPV6="${DISABLE_IPV6:-1}"
DISABLE_SELINUX="${DISABLE_SELINUX:-1}"

TMPDIR=""
OVERLAY_IMAGE=""
SEED_IMAGE=""
QEMU_PIDFILE=""
QEMU_CONSOLE_LOG=""
QEMU_ACCEL="tcg"
# Prefer a v2-capable CPU model when running under TCG to satisfy newer distros (Rocky9 glibc)
QEMU_CPU="qemu64"
QEMU_CPU_FALLBACK=""
QEMU_CPU_TCG="${QEMU_CPU_TCG:-max}"
QEMU_CPU_TCG_FALLBACK="${QEMU_CPU_TCG_FALLBACK:-qemu64}"

cleanup_on_error() {
  local exit_code=$?

  if [[ -n "${QEMU_PIDFILE}" && -f "${QEMU_PIDFILE}" ]]; then
    if pgrep -F "${QEMU_PIDFILE}" >/dev/null 2>&1; then
      kill "$(cat "${QEMU_PIDFILE}")" >/dev/null 2>&1 || true
      sleep 2
      if pgrep -F "${QEMU_PIDFILE}" >/dev/null 2>&1; then
        kill -9 "$(cat "${QEMU_PIDFILE}")" >/dev/null 2>&1 || true
      fi
    fi
    rm -f "${QEMU_PIDFILE}"
  fi

  [[ -n "${TMPDIR}" && -d "${TMPDIR}" ]] && rm -rf "${TMPDIR}"
  [[ -n "${OVERLAY_IMAGE}" && -f "${OVERLAY_IMAGE}" ]] && rm -f "${OVERLAY_IMAGE}"
  [[ -n "${SEED_IMAGE}" && -f "${SEED_IMAGE}" ]] && rm -f "${SEED_IMAGE}"

  rm -f "${STATE_FILE}"

  exit "${exit_code}"
}
trap cleanup_on_error ERR

mkdir -p "${CACHE_DIR}" "${ARTIFACTS_DIR}"

if [[ -f "${STATE_FILE}" ]]; then
  # Try to read the state file defensively; if it's malformed, just delete it.
  set +e
  # shellcheck disable=SC1090
  source "${STATE_FILE}" >/dev/null 2>&1
  SRC_STATUS=$?
  set -e
  if [[ ${SRC_STATUS} -ne 0 ]]; then
    echo ":: Existing state file is invalid; removing it (${STATE_FILE})"
    rm -f "${STATE_FILE}"
  else
    if [[ -n "${QEMU_PIDFILE:-}" && -f "${QEMU_PIDFILE}" ]]; then
      if pgrep -F "${QEMU_PIDFILE}" >/dev/null 2>&1; then
        echo "Existing VM is still running (PID $(cat "${QEMU_PIDFILE}"))." >&2
        echo "Run ${SCRIPT_DIR}/stop_vm.sh before starting a new instance." >&2
        exit 1
      fi
    fi
    rm -f "${STATE_FILE}"
  fi
fi

# Remove stale artifact directories (keeps ones with a running qemu PID)
if [[ "${CLEAR_OLD_ARTIFACTS:-1}" -eq 1 ]]; then
  for stale_dir in "${ARTIFACTS_DIR}"/vm-*; do
    [[ -d "${stale_dir}" ]] || continue
    pidfile="${stale_dir}/qemu.pid"
    if [[ -f "${pidfile}" ]] && pgrep -F "${pidfile}" >/dev/null 2>&1; then
      # Skip live VM
      continue
    fi
    rm -rf "${stale_dir}"
  done
fi

if [[ -e /dev/kvm && -r /dev/kvm && -w /dev/kvm ]]; then
  QEMU_ACCEL="kvm:tcg"
  QEMU_CPU="host"
  QEMU_CPU_FALLBACK="qemu64"
else
  echo ":: /dev/kvm unavailable, using software virtualization (TCG)"
  QEMU_CPU="${QEMU_CPU_TCG}"
  QEMU_CPU_FALLBACK="${QEMU_CPU_TCG_FALLBACK}"
fi

echo ":: Ensuring cloud image is present"
if [[ ! -f "${IMAGE_PATH}" ]]; then
  DOWNLOAD_RETRIES="${DOWNLOAD_RETRIES:-10}" # kept for backward compat; interpreted per-mirror
  MIRROR_RETRIES="${MIRROR_RETRIES:-3}"
  DOWNLOAD_DELAY="${DOWNLOAD_DELAY:-10}"
  DOWNLOAD_SPEED_TIME="${DOWNLOAD_SPEED_TIME:-90}"
  DOWNLOAD_SPEED_LIMIT="${DOWNLOAD_SPEED_LIMIT:-20480}" # bytes/sec threshold to abort and retry
  DOWNLOAD_MAX_TIME="${DOWNLOAD_MAX_TIME:-0}" # 0 = no max
  TMP_DL="${IMAGE_PATH}.partial"
  CANDIDATE_URLS=("${IMAGE_URL}" "${IMAGE_MIRRORS[@]}")
  DOWNLOAD_SUCCESS=0
  for url in "${CANDIDATE_URLS[@]}"; do
    [[ -z "${url}" ]] && continue
    echo ":: Trying image URL: ${url}"
    # reset partial when switching mirrors to avoid mismatched resumes
    rm -f "${TMP_DL}"
    ATTEMPTS=$(( MIRROR_RETRIES > 0 ? MIRROR_RETRIES : DOWNLOAD_RETRIES ))
    for attempt in $(seq 1 "${ATTEMPTS}"); do
      echo ":: Downloading image (attempt ${attempt}/${ATTEMPTS})"
      if curl --fail --location --http1.1 \
        --continue-at - \
        --retry 0 \
        --retry-all-errors \
        --retry-connrefused \
        --speed-time "${DOWNLOAD_SPEED_TIME}" \
        --speed-limit "${DOWNLOAD_SPEED_LIMIT}" \
        ${DOWNLOAD_MAX_TIME:+--max-time "${DOWNLOAD_MAX_TIME}"} \
        -o "${TMP_DL}" "${url}"; then
        mv "${TMP_DL}" "${IMAGE_PATH}"
        DOWNLOAD_SUCCESS=1
        IMAGE_URL="${url}"
        break
      fi
      if [[ ${attempt} -lt ${ATTEMPTS} ]]; then
        echo ":: Download failed; retrying in ${DOWNLOAD_DELAY}s..."
        sleep "${DOWNLOAD_DELAY}"
      else
        echo ":: Download failed after ${ATTEMPTS} attempts for ${url}" >&2
      fi
    done
    [[ ${DOWNLOAD_SUCCESS} -eq 1 ]] && break
  done
  if [[ ${DOWNLOAD_SUCCESS} -ne 1 ]]; then
    echo ":: Download failed for all mirrors." >&2
    exit 1
  fi
fi

TMPDIR="$(mktemp -d "${ARTIFACTS_DIR}/vm-XXXXXX")"
USER_DATA="${TMPDIR}/user-data"
META_DATA="${TMPDIR}/meta-data"
SEED_IMAGE="${TMPDIR}/seed.iso"
QEMU_CONSOLE_LOG="${TMPDIR}/console.log"

cat > "${USER_DATA}" <<'EOF'
#cloud-config
users:
  - name: ubuntu
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: sudo
    shell: /bin/bash
    lock_passwd: false
    passwd: $6$ur.0F/H7XkSm6y7k$kxW48kvrEEvDtZeHYCfAB.nbSZaT0s/7yQ92haFRV5gliq8knYFTrTD.6L/pouYzk2aTDsxY5GQiTLwwlXHas.
ssh_pwauth: true
package_update: true
packages:
  - python3
  - qemu-guest-agent
runcmd: []
EOF

# Append optional tweaks
if [[ "${DISABLE_IPV6}" -eq 1 ]]; then
  cat >> "${USER_DATA}" <<'EOF'
runcmd:
  - sysctl -w net.ipv6.conf.all.disable_ipv6=1
  - sysctl -w net.ipv6.conf.default.disable_ipv6=1
  - sysctl -w net.ipv6.conf.lo.disable_ipv6=1
EOF
fi

if [[ "${DISABLE_SELINUX}" -eq 1 ]]; then
  cat >> "${USER_DATA}" <<'EOF'
runcmd:
  - if command -v setenforce >/dev/null 2>&1; then setenforce 0 || true; fi
  - if [ -f /etc/selinux/config ]; then sed -i 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config; fi
EOF
fi

cat > "${META_DATA}" <<EOF
instance-id: ${VM_NAME}
local-hostname: ${VM_NAME}
EOF

echo ":: Creating cloud-init seed image"
cloud-localds "${SEED_IMAGE}" "${USER_DATA}" "${META_DATA}"

OVERLAY_IMAGE="${TMPDIR}/${VM_NAME}-overlay.qcow2"
qemu-img create -f qcow2 -F qcow2 -b "${IMAGE_PATH}" "${OVERLAY_IMAGE}" >/dev/null
qemu-img resize "${OVERLAY_IMAGE}" "${DISK_SIZE_GB}G" >/dev/null

QEMU_PIDFILE="${TMPDIR}/qemu.pid"

HOST_FWDS=()
for mapping in ${FORWARD_PORTS}; do
  host_port="${mapping%%:*}"
  guest_port="${mapping#*:}"
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn "( sport = :${host_port} )" | grep -q ":${host_port}"; then
      echo "Host port ${host_port} is already in use. Adjust FORWARD_PORTS and retry." >&2
      exit 1
    fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -ltn | awk '{print $4}' | grep -q ":${host_port}$"; then
      echo "Host port ${host_port} is already in use. Adjust FORWARD_PORTS and retry." >&2
      exit 1
    fi
  else
    if nc -z 127.0.0.1 "${host_port}" >/dev/null 2>&1; then
      echo "Host port ${host_port} is already in use. Adjust FORWARD_PORTS and retry." >&2
      exit 1
    fi
  fi
  HOST_FWDS+=("hostfwd=tcp::${host_port}-:${guest_port}")
done
HOSTFWD_OPTS=$(IFS=,; echo "${HOST_FWDS[*]}")

echo ":: Launching VM ${VM_NAME}"
launch_qemu() {
  qemu-system-x86_64 \
    -daemonize \
    -machine accel="${QEMU_ACCEL}" \
    -cpu "${QEMU_CPU}" \
    -smp "${VM_CPUS}" \
    -m "${VM_MEMORY_MB}" \
    -drive if=virtio,file="${OVERLAY_IMAGE}",format=qcow2 \
    -drive if=virtio,file="${SEED_IMAGE}",format=raw \
    -netdev user,id=net0,${HOSTFWD_OPTS} \
    -device virtio-net-pci,netdev=net0 \
    -display none \
    -serial "file:${QEMU_CONSOLE_LOG}" \
    -monitor none \
    -pidfile "${QEMU_PIDFILE}"
}

trap - ERR
set +e
launch_qemu
QEMU_EXIT=$?
set -e
trap cleanup_on_error ERR

if [[ ${QEMU_EXIT} -ne 0 && -n "${QEMU_CPU_FALLBACK}" ]]; then
  echo ":: Falling back to ${QEMU_CPU_FALLBACK}/${QEMU_ACCEL##*:}" >&2
  QEMU_CPU="${QEMU_CPU_FALLBACK}"
  QEMU_ACCEL="tcg"
  trap - ERR
  set +e
  launch_qemu
  QEMU_EXIT=$?
  set -e
  trap cleanup_on_error ERR
  if [[ ${QEMU_EXIT} -ne 0 ]]; then
    exit "${QEMU_EXIT}"
  fi
elif [[ ${QEMU_EXIT} -ne 0 ]]; then
  trap cleanup_on_error ERR
  exit "${QEMU_EXIT}"
fi
trap cleanup_on_error ERR

cat > "${STATE_FILE}" <<EOF
TMPDIR=${TMPDIR}
OVERLAY_IMAGE=${OVERLAY_IMAGE}
SEED_IMAGE=${SEED_IMAGE}
QEMU_PIDFILE=${QEMU_PIDFILE}
QEMU_CONSOLE_LOG=${QEMU_CONSOLE_LOG}
SSH_FORWARD_PORT=${SSH_FORWARD_PORT}
FORWARD_PORTS="${FORWARD_PORTS}"
EOF

echo ":: Waiting for SSH (port ${SSH_FORWARD_PORT})"
SSH_READY_TIMEOUT="${SSH_READY_TIMEOUT:-60}"
for attempt in $(seq 1 "${SSH_READY_TIMEOUT}"); do
  if nc -z 127.0.0.1 "${SSH_FORWARD_PORT}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! nc -z 127.0.0.1 "${SSH_FORWARD_PORT}" >/dev/null 2>&1; then
  echo "SSH did not become ready in time" >&2
  if [[ -n "${QEMU_CONSOLE_LOG:-}" && -f "${QEMU_CONSOLE_LOG}" ]]; then
    echo ":: Last 200 lines of console log:" >&2
    tail -n 200 "${QEMU_CONSOLE_LOG}" >&2 || true
  fi
  exit 1
fi

echo ":: Validating SSH connectivity"
SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-60}"
for attempt in $(seq 1 "${SSH_CONNECT_TIMEOUT}"); do
  if sshpass -p ubuntu ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p "${SSH_FORWARD_PORT}" ubuntu@127.0.0.1 "true" >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

if ! sshpass -p ubuntu ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p "${SSH_FORWARD_PORT}" ubuntu@127.0.0.1 "true" >/dev/null 2>&1; then
  echo "Unable to establish SSH session with guest" >&2
  if [[ -n "${QEMU_CONSOLE_LOG:-}" && -f "${QEMU_CONSOLE_LOG}" ]]; then
    echo ":: Last 200 lines of console log:" >&2
    tail -n 200 "${QEMU_CONSOLE_LOG}" >&2 || true
  fi
  exit 1
fi

trap - ERR
echo ":: VM is ready (SSH on ${SSH_FORWARD_PORT})"
