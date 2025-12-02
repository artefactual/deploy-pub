# Archivematica Acceptance Tests (AMAUATs)

## Quickstart (rootful, default Ubuntu)
1. Install Podman (use the system package). On Debian/Ubuntu:
   ```bash
   sudo apt-get update
   sudo apt-get install podman
   ```
   CI uses the runner’s preinstalled Podman; this quickstart assumes the distro Podman too.

2. Clean and set up shared venv:
   ```bash
   ../cleanup-podman.sh
   VENV_DIR=$(cd .. && pwd)/.venv-tests
   export PODMAN_COMPOSE="sudo -E env PATH=$PATH ${VENV_DIR}/bin/podman-compose"
   export PODMAN_RUN_ARGS="--cgroupns=host --systemd=always"
   ```
3. Choose base (defaults shown):
   ```bash
   export BASE_IMAGE=docker.io/library/ubuntu
   export BASE_IMAGE_TAG=24.04   # or 22.04, rocky:9, etc.
   ```
4. Build & start:
   ```bash
   $PODMAN_COMPOSE --podman-run-args="${PODMAN_RUN_ARGS}" build --pull archivematica
   $PODMAN_COMPOSE --podman-run-args="${PODMAN_RUN_ARGS}" up -d --force-recreate
   ```
5. Wait for SSH on 2222 (the container needs a short moment to finish booting):
   ```bash
   for i in {1..30}; do nc -z localhost 2222 && break; sleep 5; done
   ```
6. Verify:
   ```bash
   $PODMAN_COMPOSE ps
   sudo podman exec archivematica-acceptance-test_archivematica_1 systemctl is-system-running
   ```
7. Install Archivematica:
   ```bash
   ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_REMOTE_PORT=2222 \
     ansible-playbook -i localhost, playbook.yml -u artefactual -v
   ```

## Options / variations
- **Switch base image** (examples):
  ```bash
  export BASE_IMAGE=docker.io/library/ubuntu   ; export BASE_IMAGE_TAG=22.04
  export BASE_IMAGE=docker.io/rockylinux/rockylinux ; export BASE_IMAGE_TAG=9.6
  ```
- **Rootless:** 
  ```bash
  export PODMAN_COMPOSE=podman-compose
  XDG_RUNTIME_DIR=$(mktemp -d /tmp/podman-run-XXXX)
  BASE_IMAGE=docker.io/library/ubuntu BASE_IMAGE_TAG=24.04 \
  $PODMAN_COMPOSE -f compose.yaml -f compose.rootless.yaml up --detach --force-recreate
  ```
- **Shared podman-compose venv:** created by `../cleanup-podman.sh`. Recreate manually with:
  ```bash
  rm -rf ../.venv-tests
  python3 -m venv ../.venv-tests
  ../.venv-tests/bin/python -m pip install -r requirements.txt
  ```
- **Cleanup everything:** `./tests/cleanup-podman.sh`

## Installing Ansible (project venv)
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
ansible-galaxy install -f -p roles/ -r requirements.yml
```

## Installing Archivematica

Run the Archivematica installation playbook:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_REMOTE_PORT=2222
ansible-playbook -i localhost, playbook.yml \
    -u artefactual \
    -v
```

Add the `artefactual` user to the `archivematica` group so it can copy AIPs
from the shared directory:

```shell
podman-compose exec --user root archivematica usermod -a -G archivematica artefactual
```

The AMAUATs expect the Archivematica sample data to be in the
`/home/archivematica` directory:

```shell
podman-compose exec --user root archivematica ln -s /home/artefactual /home/archivematica
```

## Testing the Archivematica installation

Call an Archivematica API endpoint:

```shell
curl --header "Authorization: ApiKey admin:this_is_the_am_api_key" http://localhost:8000/api/processing-configuration/
```

Call a Storage Service API endpoint:

```shell
curl --header "Authorization: ApiKey admin:this_is_the_ss_api_key" http://localhost:8001/api/v2/pipeline/
```

## Running an Acceptance Test

Clone the AMAUATs repository:

```shell
git clone https://github.com/artefactual-labs/archivematica-acceptance-tests AMAUATs
cd AMAUATs
```

Install the AMAUATs requirements:

```shell
python3 -m pip install -r requirements.txt
```

Run any [feature file](https://github.com/artefactual-labs/archivematica-acceptance-tests/tree/qa/1.x/features/black_box)
in the AMAUATs using its filename. This example shows how to run the
`create-aip.feature` file with `Chrome`. You need to pass your SSH identity file:

```shell
env HEADLESS=1 behave -i create-aip.feature \
    -v \
    --no-capture \
    --no-capture-stderr \
    --no-logcapture \
    --no-skipped \
    -D am_version=1.9 \
    -D driver_name=Chrome \
    -D am_username=admin \
    -D am_password=archivematica \
    -D am_url=http://localhost:8000/ \
    -D am_api_key="this_is_the_am_api_key" \
    -D ss_username=admin \
    -D ss_password=archivematica \
    -D ss_api_key="this_is_the_ss_api_key" \
    -D ss_url=http://localhost:8001/ \
    -D home=artefactual \
    -D server_user=artefactual \
    -D transfer_source_path=/home/artefactual/archivematica-sampledata/TestTransfers/acceptance-tests \
    -D ssh_identity_file=$HOME/.ssh/id_ed25519
```

Some feature files (AIP encryption and UUIDs for directories) copy AIPs from
the remote host using `scp` but they assume port 22 is used for the SSH service.
You can set this in your `$HOME/.ssh/config` file to make them work with port
2222:

```console
Host localhost
    Port 2222
```
