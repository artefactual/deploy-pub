# DIP upload test (KVM)

The Archivematica + AtoM DIP upload scenario now runs inside a single KVM/QEMU
guest instead of Podman Compose.

## Host requirements

- KVM-enabled qemu (`qemu-system-x86_64`), `qemu-utils`, `cloud-image-utils`
- `sshpass`, `curl`, Python 3 with `venv`
- Access to `/dev/kvm` recommended

### Tunable defaults
Set before `./run.sh` to override defaults:
- `VM_CPUS` (4 in CI), `VM_MEMORY_MB` (10240 in CI)
- `SSH_READY_TIMEOUT` (180), `SSH_CONNECT_TIMEOUT` (180)
- `IMAGE_URL` / `IMAGE_MIRRORS` (primary and mirror cloud images)
- `MIRROR_RETRIES` (10)
- `KVM_ACCEL` (auto; use `tcg` to mimic GitHub runners without /dev/kvm)
- `SKIP_CLEANUP=1` to keep the VM up; stop later with `STATE_FILE=.../artifacts/dip_upload_vm.env tests/kvm/stop_vm.sh`
- `DISABLE_IPV6=1` (default) – disable IPv6 in the guest.
- `DISABLE_SELINUX=1` (default) – set SELinux to permissive.

### SSH into the local VM
- Host: `127.0.0.1`
- Port: `2222` (override with `SSH_FORWARD_PORT`)
- User: `ubuntu`, Password: `ubuntu`
```bash
ssh -p 2222 ubuntu@127.0.0.1
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
ansible-galaxy install -f -p roles/ -r requirements.yml
```

## Provision the VM

```bash
cd tests/dip-upload
# Customize if needed: VM_CPUS, VM_MEMORY_MB, FORWARD_PORTS
./run.sh
```

### Use a different guest OS image
Set `IMAGE_URL` to a cloud-init qcow2:
- Ubuntu 24.04 (default): https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
- Ubuntu 22.04: https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
- Ubuntu 20.04: https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img
- Rocky 9: https://download.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-GenericCloud-Base.latest.x86_64.qcow2
- Rocky 8: https://download.rockylinux.org/pub/rocky/8/images/x86_64/Rocky-8-GenericCloud-Base.latest.x86_64.qcow2

Example:
```bash
IMAGE_URL=https://cloud-images.ubuntu.com/focal/current/focal-server-cloudimg-amd64.img \
DISK_SIZE_GB=20 VM_MEMORY_MB=8192 ./run.sh
```

Port forwards:

- `localhost:8000` → Archivematica dashboard (guest 80)
- `localhost:8001` → Storage Service (guest 8000)
- `localhost:9000` → AtoM (guest 9000)
- SSH on `localhost:2222`

Keep the VM running for manual steps:

```bash
SKIP_CLEANUP=1 ./run.sh
```

Stop the VM later:

```bash
STATE_FILE=tests/dip-upload/artifacts/dip_upload_vm.env \
  tests/kvm/stop_vm.sh
```

## Verify the installations

```bash
# Archivematica
curl --header "Authorization: ApiKey admin:this_is_the_am_api_key" http://localhost:8000/api/processing-configuration/
curl --header "Authorization: ApiKey admin:this_is_the_ss_api_key" http://localhost:8001/api/v2/pipeline/

# AtoM
curl --header "REST-API-Key: this_is_the_atom_dip_upload_api_key" http://localhost:9000/index.php/api/informationobjects
```

## Run the DIP upload exercise

```bash
# Configure Archivematica processing
curl \
  --header "Authorization: ApiKey admin:this_is_the_am_api_key" \
  --request POST \
  --data "{ \
      \"name\": \"dip-upload-test\", \
      \"path\": \"$(echo -n '/home/ubuntu/archivematica-sampledata/SampleTransfers/DemoTransferCSV' | base64 -w 0)\", \
      \"type\": \"standard\", \
      \"processing_config\": \"dipupload\", \
      \"access_system_id\": \"example-item\" \
  }" \
  http://localhost:8000/api/v2beta/package

sleep 120

# Validate AtoM received the object
curl \
  --header "REST-API-Key: this_is_the_atom_dip_upload_api_key" \
  --silent \
  http://localhost:9000/index.php/api/informationobjects/beihai-guanxi-china-1988 | \
  python3 -m json.tool | grep '\"parent\": \"example-item\"'
```
