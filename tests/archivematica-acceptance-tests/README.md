# Archivematica Acceptance Tests (AMAUATs)

This test environment now runs inside a single KVM/QEMU guest instead of a
Podman Compose stack.

## Host requirements

- KVM-enabled qemu (`qemu-system-x86_64`), `qemu-utils`, `cloud-image-utils`
  (`cloud-localds`)
- Access to `/dev/kvm` (for hardware acceleration) or fallback to TCG
- `sshpass`, `curl`, Python 3 (with `venv`)
- Latest Google Chrome with chromedriver or Firefox with geckodriver
- 7-Zip

### Tunable defaults
The KVM launcher and playbook respect these environment variables (defaults shown):

- `VM_CPUS=4`, `VM_MEMORY_MB=10240` (GitHub Actions); adjust for local runs as needed.
- `SSH_READY_TIMEOUT=180`, `SSH_CONNECT_TIMEOUT=180` – wait times for SSH to come up.
- `IMAGE_URL` / `IMAGE_MIRRORS` – primary image and mirrors (Rocky uses CloudStack as primary for speed).
- `MIRROR_RETRIES=10` – attempts per mirror.
- `KVM_ACCEL` – auto‐detects; set `tcg` to mimic GitHub runners without `/dev/kvm`.
- `SKIP_CLEANUP=1` – leave the VM running; stop later with `STATE_FILE=.../artifacts/archivematica_vm.env tests/kvm/stop_vm.sh`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
ansible-galaxy install -f -p roles/ -r requirements.yml
```

## Start the VM and provision Archivematica

```bash
cd tests/archivematica-acceptance-tests
# Optional: adjust VM resources or forwards
# export VM_CPUS=4 VM_MEMORY_MB=8192 FORWARD_PORTS="2222:22 8000:80 8001:8000"
./run.sh
```

### Use a different guest OS image
Point `IMAGE_URL` to any cloud-init qcow2. Tested options:
- Ubuntu 24.04 (default): https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
- Ubuntu 22.04: https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
- Ubuntu 20.04: https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img
- Rocky 9: https://download.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-GenericCloud-Base.latest.x86_64.qcow2
- Rocky 8: https://download.rockylinux.org/pub/rocky/8/images/x86_64/Rocky-8-GenericCloud-Base.latest.x86_64.qcow2

Example:
```bash
IMAGE_URL=https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img \
DISK_SIZE_GB=20 VM_CPUS=4 VM_MEMORY_MB=8192 ./run.sh
```

What `run.sh` does:

- Boots an Ubuntu 24.04 cloud image with KVM (SSH on `localhost:2222`)
- Forwards host ports `8000 -> guest:80` (Dashboard) and `8001 -> guest:8000`
  (Storage Service)
- Installs Galaxy roles/collections and runs `playbook.yml` against the guest.
- Stops the VM on exit unless `SKIP_CLEANUP=1`.

To keep the VM running (for debugging or AMAUAT runs):

```bash
SKIP_CLEANUP=1 ./run.sh
```

Stop a running VM later:

```bash
STATE_FILE=tests/archivematica-acceptance-tests/artifacts/archivematica_vm.env \
  tests/kvm/stop_vm.sh
```

## Smoke checks

```bash
curl --header "Authorization: ApiKey admin:this_is_the_am_api_key" http://localhost:8000/api/processing-configuration/
curl --header "Authorization: ApiKey admin:this_is_the_ss_api_key" http://localhost:8001/api/v2/pipeline/
```

## Running AMAUATs

```bash
git clone https://github.com/artefactual-labs/archivematica-acceptance-tests AMAUATs
cd AMAUATs
python3 -m pip install -r requirements.txt

env HEADLESS=1 behave -i create-aip.feature \
  --no-capture --no-capture-stderr --no-logcapture --no-skipped \
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
  -D home=ubuntu \
  -D server_user=ubuntu \
  -D transfer_source_path=/home/ubuntu/archivematica-sampledata/TestTransfers/acceptance-tests \
  -D ssh_identity_file=$HOME/.ssh/id_rsa
```

If you need to use a non-default SSH port for AMAUATs, add this to your
`~/.ssh/config`:

```
Host localhost
  Port 2222
```
