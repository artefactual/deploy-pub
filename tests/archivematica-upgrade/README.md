# Archivematica playbook upgrade test

The test installs the stable version of Archivematica on a libvirt virtual
machine and then upgrades that installation to the QA version, including the
Percona Server upgrade that the QA variables file requires.

The virtual machine runs a complete systemd instance, so the upgrade can
restart the services it replaces.

## Software requirements

- KVM and libvirt
- virt-install
- cloud-localds
- qemu-img
- Python 3
- curl
- jq

On Debian or Ubuntu, install them with:

```shell
sudo apt install \
    cloud-image-utils \
    jq \
    libvirt-clients \
    libvirt-daemon-system \
    qemu-kvm \
    qemu-utils \
    virtinst
```

## Host setup

The test uses the system libvirt connection, `qemu:///system`, because the
virtual machine has to be reachable from the host on its own address. The
session connection, `qemu:///session`, runs QEMU without a routable network
and is not supported.

Add your account to the `libvirt` and `kvm` groups and log in again:

```shell
sudo usermod --append --groups libvirt,kvm "$USER"
```

Check that the connection works and that the `default` NAT network is
active:

```shell
virsh --connect qemu:///system net-list --all
```

Start the network if it is inactive:

```shell
virsh --connect qemu:///system net-start default
virsh --connect qemu:///system net-autostart default
```

QEMU runs the virtual machine under its own account, so it cannot read disk
images stored in a home directory. Create the disk image directory below
`/var/lib/libvirt/images` once, owned by your account and shared with the
`kvm` group:

```shell
sudo mkdir -p /var/lib/libvirt/images/deploy-pub-tests
sudo chown "$USER":kvm /var/lib/libvirt/images/deploy-pub-tests
sudo chmod 2770 /var/lib/libvirt/images/deploy-pub-tests
```

The helper keeps the virtual machine disks and the cached cloud images
there. Set `VM_STORAGE_DIR` to use another directory.

`virt-install` warns that the hypervisor may not be able to access those
disk images. The warning does not account for the supplementary groups of
the QEMU account, which reaches the directory through the `kvm` group, so it
can be ignored.

## Tested environments

The workflow runs the upgrade on each of these environments:

- Ubuntu 22.04
- Ubuntu 24.04
- Rocky Linux 8
- Rocky Linux 9

## Running the workflow manually

The GitHub Actions workflow exposes an operating-system dropdown that defaults
to `all`. Select an operating system to run only its upgrade.

Scheduled, pull-request, and master-branch push runs use the default and test
all supported operating systems.

The job stops before it installs anything when `/dev/kvm` is missing, rather
than falling back to software emulation and taking hours to reach the same
result.

## Installing Ansible

Create a virtual environment and activate it:

```shell
python3 -m venv .venv
source .venv/bin/activate
```

Install the Python requirements:

```shell
python3 -m pip install -r requirements.txt
```

When using the `rocky8` environment, pin Ansible Core to 2.16.x:

```shell
python3 -m pip install -r requirements.txt \
    -c ../common/constraints-rocky8.txt
```

## Creating the virtual machine

The virtual machine defaults to Ubuntu 22.04. Set `VM_OS` to select another
tested environment:

```shell
export VM_OS=jammy
```

The accepted values are `jammy`, `noble`, `rocky8` and `rocky9`.

Create the virtual machine:

```shell
../common/libvirt-vm create
```

The helper downloads and caches the cloud image, copies it into a 20 GiB
disk, boots the domain on the `default` network and waits until cloud-init
has created the `ubuntu` account with your `~/.ssh/id_rsa.pub` key and
passwordless sudo.

Record the address the rest of the commands use:

```shell
export VM_IP=$(../common/libvirt-vm ip)
```

Run the helper without a command to see every variable that overrides the
domain name, the memory, the virtual CPUs, the disk size and the SSH key.

## Installing the stable version of Archivematica

Install the requirements of the stable version:

```shell
../common/prepare-ansible-roles --target vm \
    ../../playbooks/archivematica-noble/requirements.yml
```

The `vm` target installs the roles without the container workarounds the
Podman test suites need, including the one that stops the Percona role from
restarting MySQL.

Run the Archivematica installation playbook passing the stable version as the
`am_version` variable and the proper URLs for the virtual machine:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook -i "${VM_IP}," playbook.yml \
    -u ubuntu \
    -e "am_version=1.18" \
    -e "archivematica_src_configure_am_site_url=http://${VM_IP}" \
    -e "archivematica_src_configure_ss_url=http://${VM_IP}:8000" \
    -v
```

## Testing the stable version of Archivematica

Get the Archivematica stable version:

```shell
curl \
    --silent \
    --dump-header - \
    --header "Authorization: ApiKey admin:this_is_the_am_api_key" \
    "http://${VM_IP}/api/processing-configuration/" \
    | grep X-Archivematica-Version
```

Check the Archivematica and Storage Service APIs:

```shell
AM_URL="http://${VM_IP}" \
SS_URL="http://${VM_IP}:8000" \
    ../common/check-archivematica-apis
```

## Checkpointing the stable installation

Installing the stable version takes about twenty minutes. Save a checkpoint
once it passes so that a failed upgrade can be retried in seconds instead:

```shell
../common/libvirt-vm snapshot stable
```

The virtual machine pauses while libvirt writes its memory into the disk
image, so the checkpoint needs as much free space as `VM_MEMORY`.

Checkpoints are not available for the `rocky9` guest. It boots from UEFI
firmware, which libvirt cannot include in an internal snapshot, so recreate
that virtual machine instead of checkpointing it.

Return to the checkpoint after a failed upgrade:

```shell
../common/libvirt-vm revert stable
```

The checkpoint stores the memory of the virtual machine, so it restores a
running Archivematica and the upgrade can be run again immediately. List and
delete the checkpoints with:

```shell
../common/libvirt-vm snapshots
../common/libvirt-vm forget stable
```

Retry an upgrade from a checkpoint rather than from the state a failed
upgrade left behind. A partially configured package, for example, is a state
that no real installation reaches, so the retry would not test the upgrade.

## Upgrading to the QA version of Archivematica

Delete the requirements directory used for the stable version:

```shell
rm -rf roles
```

Install the requirements of the QA version:

```shell
../common/prepare-ansible-roles --target vm \
    ../../playbooks/archivematica-noble/requirements-qa.yml
```

Run the Archivematica installation playbook passing the QA version as the
`am_version` variable, the proper URLs for the virtual machine and the tags
to upgrade installations:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook -i "${VM_IP}," playbook.yml \
    -u ubuntu \
    -e "am_version=qa" \
    -e "archivematica_src_configure_am_site_url=http://${VM_IP}" \
    -e "archivematica_src_configure_ss_url=http://${VM_IP}:8000" \
    -e "elasticsearch_version=8.19.2" \
    -t "elasticsearch,percona,archivematica-src" \
    -v
```

The `percona` tag upgrades Percona Server from 8.0 to 8.4, which is the
version the `mysql_version_minor` variable of the QA variables file
requires.

## Testing the QA version of Archivematica

Get the Archivematica QA version:

```shell
curl \
    --silent \
    --dump-header - \
    --header "Authorization: ApiKey admin:this_is_the_am_api_key" \
    "http://${VM_IP}/api/processing-configuration/" \
    | grep X-Archivematica-Version
```

Check the Archivematica and Storage Service APIs:

```shell
AM_URL="http://${VM_IP}" \
SS_URL="http://${VM_IP}:8000" \
    ../common/check-archivematica-apis
```

## Inspecting a failed upgrade

Open a session on the virtual machine:

```shell
../common/libvirt-vm ssh
```

Read the journal, the failed units or the MySQL error log:

```shell
../common/libvirt-vm ssh "sudo journalctl --no-pager"
../common/libvirt-vm ssh "sudo systemctl --failed --no-pager --full"
../common/libvirt-vm ssh "sudo cat /var/log/mysql/error.log"
```

Attach to the serial console when the virtual machine does not boot:

```shell
virsh --connect qemu:///system console deploy-pub-jammy
```

## Destroying the virtual machine

```shell
../common/libvirt-vm destroy
```

The cached cloud images are kept for the next run.
