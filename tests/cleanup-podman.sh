#!/usr/bin/env bash
set -euo pipefail

# Clean up podman-compose projects used by this repo's test suites.
# Usage: ./tests/cleanup-podman.sh [compose-file ...]
# If no files are passed, it cleans the standard test compose files.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

# Shared virtualenv used by all test utilities; override with VENV_DIR if needed.
VENV_DIR=${VENV_DIR:-"${REPO_ROOT}/.venv-tests"}
# Default to podman-compose inside the shared venv; honour PODMAN_COMPOSE if set.
PODMAN_COMPOSE=${PODMAN_COMPOSE:-"${VENV_DIR}/bin/podman-compose"}

ensure_venv() {
  # Only bootstrap when the default (shared) podman-compose is used.
  if [[ "${PODMAN_COMPOSE}" != "${VENV_DIR}/bin/podman-compose" ]]; then
    return
  fi
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo ":: Creating shared virtualenv at ${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
  fi
  echo ":: Ensuring podman-compose is installed in ${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip >/dev/null
  # Pin to the same commit used by the test requirements files.
  "${VENV_DIR}/bin/python" -m pip install -q \
    "git+https://github.com/containers/podman-compose.git@2681566580b4eaadfc5e6000ad19e49e56006e2b#egg=podman-compose"
}

ensure_venv

if [[ "$#" -gt 0 ]]; then
  compose_files=("$@")
else
  compose_files=(
    "tests/archivematica-acceptance-tests/compose.yaml"
    "tests/archivematica-upgrade/compose.yaml"
    "tests/dip-upload/compose.yaml"
  )
fi

# Containers/images that can linger when running podman manually
extra_containers=(
  am-test
  am-upgrade-test
  dip-upload-test
)
extra_images=(
  localhost/archivematica-acceptance-test_archivematica:latest
  localhost/archivematica-upgrade_archivematica:latest
  localhost/dip-upload_archivematica:latest
  localhost/dip-upload_atom:latest
)
extra_pods=(
  pod_archivematica-acceptance-test
  pod_archivematica-upgrade-test
  pod_dip-upload-test
)

for compose in "${compose_files[@]}"; do
  if [[ ! -f "${compose}" ]]; then
    echo "Skip missing compose file: ${compose}"
    continue
  fi
  project_name=$(awk '/^name:/{print $2; exit}' "${compose}")
  echo ":: Cleaning project ${project_name:-unknown} (${compose})"
  ${PODMAN_COMPOSE} -f "${compose}" down -v --remove-orphans || true
done

echo ":: Removing known manual containers"
for name in "${extra_containers[@]}"; do
  sudo podman rm -f "${name}" >/dev/null 2>&1 || true
done

echo ":: Removing lingering pods"
for pod in "${extra_pods[@]}"; do
  sudo podman pod rm -f "${pod}" >/dev/null 2>&1 || true
done

echo ":: Removing local test images"
for image in "${extra_images[@]}"; do
  sudo podman rmi -f "${image}" >/dev/null 2>&1 || true
done

echo ":: Pruning dangling podman artifacts"
sudo podman image prune -f >/dev/null || true
sudo podman volume prune -f >/dev/null || true
sudo podman container prune -f >/dev/null || true
