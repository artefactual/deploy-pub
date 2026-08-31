# Shared test infrastructure

This directory contains infrastructure shared by the Archivematica acceptance,
DIP upload and upgrade test suites.

The suites run the Ansible roles on a Podman container or on a libvirt
virtual machine. Each suite documents the one it uses.

`Dockerfile` builds the systemd and SSH test container for these operating
systems:

- Ubuntu 22.04
- Ubuntu 24.04
- Rocky Linux 8
- Rocky Linux 9

Each container suite keeps its own Compose file and passes the image name,
image tag and suite-specific SSH public key path as build arguments.

`libvirt-vm` creates the equivalent virtual machine for those operating
systems from their cloud images. Run it without a command to see the
variables that select the operating system and size the domain.

Rocky Linux 8 requires Ansible Core 2.16. The shared
`constraints-rocky8.txt` file keeps the acceptance and upgrade tests on that
compatible release.

The helper commands install and adjust the Ansible roles, create and remove
the virtual machine, check the Archivematica APIs and collect container,
journal and application logs. Run them from a test suite directory, for
example:

```shell
../common/prepare-ansible-roles requirements.yml
../common/prepare-ansible-roles --target vm requirements.yml
../common/libvirt-vm create
../common/libvirt-vm snapshot stable
../common/libvirt-vm revert stable
../common/check-archivematica-apis
../common/wait-for-archivematica-transfer "$TRANSFER_UUID"
../common/collect-test-logs logs archivematica
../common/collect-vm-test-logs logs
../common/libvirt-vm destroy
```

`prepare-ansible-roles` defaults to `--target podman`, which adjusts the
roles for rootless Podman: it stops the Percona role from restarting MySQL
and disables the memcached sysctl reload. `--target vm` installs the roles
without those adjustments and keeps the fixes both environments need.

Pass each Compose service that should be inspected to `collect-test-logs`.
`collect-vm-test-logs` collects the same journal, failed unit and application
logs from a virtual machine over SSH, and takes only the output directory.
Both collectors are best-effort so services or application logs that do not
exist during a partial installation do not hide the original test failure.
