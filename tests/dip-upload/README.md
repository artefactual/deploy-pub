# DIP Upload Test

## Quickstart (rootful, default Ubuntu)
1. Clean & shared venv:
   ```bash
   ../cleanup-podman.sh
   VENV_DIR=$(cd .. && pwd)/.venv-tests
   export PODMAN_COMPOSE="sudo -E env PATH=$PATH ${VENV_DIR}/bin/podman-compose"
   export PODMAN_RUN_ARGS="--cgroupns=host --systemd=always"
   ```
2. Base image (defaults):
   ```bash
   export BASE_IMAGE=docker.io/library/ubuntu
   export BASE_IMAGE_TAG=24.04   # or 22.04, rocky:9, ubi:9.4, etc.
   ```
3. Build & start:
   ```bash
   $PODMAN_COMPOSE --podman-run-args="${PODMAN_RUN_ARGS}" build --pull archivematica atom
   $PODMAN_COMPOSE --podman-run-args="${PODMAN_RUN_ARGS}" up -d --force-recreate
   ```
4. Wait for SSH on Archivematica (2222) and AtoM (9222):
   ```bash
   for port in 2222 9222; do
     for i in {1..30}; do nc -z localhost "$port" && break; sleep 5; done
   done
   ```
5. Verify:
   ```bash
   $PODMAN_COMPOSE ps
   sudo podman exec dip-upload_archivematica_1 systemctl is-system-running
   ```
6. Run playbooks as per test instructions.

## Options
- Switch base image:
  ```bash
  export BASE_IMAGE=docker.io/library/ubuntu ; export BASE_IMAGE_TAG=22.04
  export BASE_IMAGE=docker.io/rockylinux/rockylinux ; export BASE_IMAGE_TAG=9.6
  ```
- Shared podman-compose venv:
  ```bash
  rm -rf ../.venv-tests
  python3 -m venv ../.venv-tests
  ../.venv-tests/bin/python -m pip install -r ../requirements.txt
  ```
- Project Ansible venv:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  python3 -m pip install -r requirements.txt
  ansible-galaxy install -f -p roles/ -r requirements.yml
  ```
- Cleanup everything: `./tests/cleanup-podman.sh`
