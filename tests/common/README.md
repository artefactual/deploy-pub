# Shared Podman test infrastructure

This directory contains infrastructure shared by the Archivematica acceptance,
DIP upload and upgrade test suites.

`Dockerfile` builds the systemd and SSH test container for these operating
systems:

- Ubuntu 22.04
- Ubuntu 24.04
- Rocky Linux 8
- Rocky Linux 9

Each suite keeps its own Compose file and passes the image name, image tag and
suite-specific SSH public key path as build arguments.

Rocky Linux 8 requires Ansible Core 2.16. The shared
`constraints-rocky8.txt` file keeps the acceptance and upgrade tests on that
compatible release.

The helper commands install and adjust the Ansible roles for rootless Podman,
check the Archivematica APIs and collect systemd journal logs. Run them from a
test suite directory, for example:

```shell
../common/prepare-ansible-roles requirements.yml
../common/check-archivematica-apis
../common/wait-for-archivematica-transfer "$TRANSFER_UUID"
../common/collect-journal-log archivematica archivematica-mcp-client \
    logs/mcp-client.log
```
