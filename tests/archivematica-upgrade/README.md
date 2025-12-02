# Archivematica Upgrade Test

## Quickstart (rootful, default Ubuntu)
1. Clean & shared venv:
   ```bash
   ../cleanup-podman.sh
   VENV_DIR=$(cd .. && pwd)/.venv-tests
   export PODMAN_COMPOSE="sudo -E env PATH=$PATH ${VENV_DIR}/bin/podman-compose"
   export PODMAN_RUN_ARGS="--cgroupns=host --systemd=always"
   ```
2. Base image (defaults shown):
   ```bash
   export BASE_IMAGE=docker.io/library/ubuntu
   export BASE_IMAGE_TAG=24.04   # or 22.04, rocky:9, ubi:9.4, etc.
   ```
3. Build & start:
   ```bash
   $PODMAN_COMPOSE --podman-run-args="${PODMAN_RUN_ARGS}" build --pull archivematica
   $PODMAN_COMPOSE --podman-run-args="${PODMAN_RUN_ARGS}" up -d --force-recreate
   ```
4. Wait for SSH on 2222:
   ```bash
   for i in {1..30}; do nc -z localhost 2222 && break; sleep 5; done
   ```
5. Verify:
   ```bash
   $PODMAN_COMPOSE ps
   sudo podman exec archivematica-upgrade-test_archivematica_1 systemctl is-system-running
   ```
6. Run upgrade playbook:
   ```bash
   ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_REMOTE_PORT=2222 \
     ansible-playbook -i localhost, playbook.yml \
     -u artefactual \
     -e "am_version=1.16" \
     -e "archivematica_src_configure_am_site_url=http://archivematica" \
     -e "archivematica_src_configure_ss_url=http://archivematica:8000" \
     -v
   ```

## Options
- Switch base image:
  ```bash
  export BASE_IMAGE=docker.io/library/ubuntu            ; export BASE_IMAGE_TAG=22.04
  export BASE_IMAGE=docker.io/rockylinux/rockylinux     ; export BASE_IMAGE_TAG=9.6
  ```
- Shared podman-compose venv (if you need to recreate):
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
  ```
- Cleanup everything: `./tests/cleanup-podman.sh`
