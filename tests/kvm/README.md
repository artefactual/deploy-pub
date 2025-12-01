# KVM launcher knobs

The helper scripts in `tests/kvm/` are driven by environment variables so you can tune downloads, timeouts, and VM resources without editing the scripts. Common knobs:

- `IMAGE_URL` – cloud image URL (QCOW2 with cloud-init).  
- `IMAGE_MIRRORS` – space‑separated mirror URLs; tried in order.  
- `MIRROR_RETRIES` – attempts per mirror (default 10).  
- `DOWNLOAD_RETRIES`, `DOWNLOAD_DELAY`, `DOWNLOAD_SPEED_TIME`, `DOWNLOAD_SPEED_LIMIT` – curl retry/back‑off controls.  
- `VM_CPUS`, `VM_MEMORY_MB`, `DISK_SIZE_GB` – guest resources.  
- `SSH_READY_TIMEOUT`, `SSH_CONNECT_TIMEOUT` – seconds to wait for SSH port/up.  
- `KVM_ACCEL` – force `tcg` to mimic GitHub runners without `/dev/kvm`; default auto `kvm:tcg`.  
- `FORWARD_PORTS` / `SSH_FORWARD_PORT` – host→guest port mappings (default `2222:22 8000:80 8001:8000`).
- `SKIP_CLEANUP=1` – leave the VM running after `run.sh`; use `stop_vm.sh` (with the suite’s `STATE_FILE`) to stop it later.

Downloads are cached under `tests/kvm/.cache`. Each suite writes its own `STATE_FILE` in its `artifacts/` directory; `stop_vm.sh` can stop a VM without the state file and will also kill stray `qemu` processes if found.
