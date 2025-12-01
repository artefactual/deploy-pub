# Archivematica playbook upgrade test (KVM)

This scenario now runs inside a single KVM/QEMU VM instead of Podman Compose.

## Host requirements

- KVM-enabled qemu (`qemu-system-x86_64`), `qemu-utils`, `cloud-image-utils`
- `sshpass`, `curl`, Python 3 with `venv`
- Access to `/dev/kvm` recommended

### Tunable defaults
These env vars can be set before `./run.sh` (defaults in parentheses):
- `VM_CPUS` (4 in CI), `VM_MEMORY_MB` (10240 in CI)
- `SSH_READY_TIMEOUT` (180), `SSH_CONNECT_TIMEOUT` (180)
- `IMAGE_URL` / `IMAGE_MIRRORS` (cloud image + mirrors)
- `MIRROR_RETRIES` (10)
- `KVM_ACCEL` (auto; set `tcg` to mimic GitHub runners without /dev/kvm)
- `SKIP_CLEANUP=1` to leave the VM running; stop later with `STATE_FILE=.../artifacts/archivematica_vm.env tests/kvm/stop_vm.sh`
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

## Start the VM

```bash
cd tests/archivematica-upgrade
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
IMAGE_URL=https://download.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-GenericCloud-Base.latest.x86_64.qcow2 \
DISK_SIZE_GB=20 VM_MEMORY_MB=8192 ./run.sh
```

Port forwards:

- `localhost:8000` → Archivematica dashboard (guest port 80)
- `localhost:8001` → Storage Service (guest port 8000)
- SSH on `localhost:2222`

To leave the VM running for debugging or for the second upgrade run:

```bash
SKIP_CLEANUP=1 ./run.sh
```

Stop the VM later:

```bash
STATE_FILE=tests/archivematica-upgrade/artifacts/archivematica_vm.env \
  tests/kvm/stop_vm.sh
```

## Running the upgrade scenario

1. **Install stable Archivematica**

```bash
ANSIBLE_HOST_KEY_CHECKING=False \
  ./run.sh -e "am_version=1.16" \
  -e "archivematica_src_configure_am_site_url=http://localhost" \
  -e "archivematica_src_configure_ss_url=http://localhost:8000" \
  -t "archivematica-src,elasticsearch,percona,gearman,nginx"
```

2. **Exercise the stable install**

```bash
curl --header "Authorization: ApiKey admin:this_is_the_am_api_key" http://localhost:8000/api/processing-configuration/
curl --header "Authorization: ApiKey admin:this_is_the_ss_api_key" http://localhost:8001/api/v2/pipeline/
```

3. **Upgrade to QA**

```bash
./run.sh \
  -e "am_version=qa" \
  -e "archivematica_src_configure_am_site_url=http://localhost" \
  -e "archivematica_src_configure_ss_url=http://localhost:8000" \
  -e "elasticsearch_version=8.19.2" \
  -t "elasticsearch,archivematica-src"
```

If you don’t pass `am_version`, the playbook defaults to `am_version=1.18`.

4. **Re-test**

```bash
curl --header "Authorization: ApiKey admin:this_is_the_am_api_key" http://localhost:8000/api/processing-configuration/
curl --header "Authorization: ApiKey admin:this_is_the_ss_api_key" http://localhost:8001/api/v2/pipeline/
```
