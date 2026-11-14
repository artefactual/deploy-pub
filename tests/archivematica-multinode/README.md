# Archivematica multinode test

The test installs the Storage Service and an Archivematica pipeline on
different hosts and runs four MCPClient instances on the pipeline host. It
then processes four transfers at the same time, one for each instance, and
checks that the Storage Service host stores the resulting AIPs.

The `archivematica_src_am_mcpclient_instances` variable of the `pipeline`
host in `inventory.yml` sets the number of MCPClient instances, and the
number of transfers follows it.

The installation follows the "Deploy separate SS and pipeline" procedure of
the `archivematica-src` role. The hosts do not share storage: the Storage
Service reaches the shared directory of the pipeline over SSH, through a
pipeline local filesystem space.

The hosts are Podman containers on one Compose network:

- `storage-service` runs MySQL, Nginx and the Storage Service. It also holds
  the transfer source and the AIP store.
- `pipeline` runs MySQL, Elasticsearch, Gearman, ClamAV, Nginx, the
  dashboard, MCPServer and the MCPClient instances.

Ansible reaches both hosts through SSH ports published on localhost, so it
cannot resolve the names the hosts use for each other. The role needs that
for one task, the scan of the SSH host key of the pipeline, and
`../common/prepare-ansible-roles` makes the Storage Service host run that
scan instead.

## Software requirements

- Podman
- uv
- curl
- jq

## Tested environments

The workflow runs the test on each of these operating systems:

- Ubuntu 22.04
- Ubuntu 24.04
- Rocky Linux 9

It installs these versions on each of them:

- `1.18`: Archivematica 1.18.0 and Storage Service 0.24.0
- `qa`: the `qa/1.x` and `qa/0.x` branches

Both hosts of an environment run the same operating system.

## Running the workflow manually

The GitHub Actions workflow exposes a version dropdown and an
operating-system dropdown. Both default to `all`. Select a version or an
operating system to narrow either matrix axis.

Scheduled and pull-request runs use both defaults and test all versions on
all operating systems.

## Installing Ansible

Create the virtual environment with the locked Python requirements and
activate it:

```shell
uv sync --locked
source .venv/bin/activate
```

## Starting the Compose environment

Copy your SSH public key as the `ssh_pub_key` file next to the Compose file:

```shell
cp $HOME/.ssh/id_rsa.pub ssh_pub_key
```

Set the Docker image and tag to use for both hosts:

```shell
export DOCKER_IMAGE_NAME=ubuntu
export DOCKER_IMAGE_TAG=22.04
```

Start the Compose services:

```shell
podman-compose up --detach
```

## Installing the Ansible roles

Set the version to install, either `1.18` or `qa`:

```shell
export AM_VERSION=1.18
```

Install the playbook requirements of that version:

```shell
../common/prepare-ansible-roles "requirements-${AM_VERSION}.yml"
```

## Installing the Storage Service

Run the Storage Service playbook without the tasks that connect it to the
pipeline, which does not exist yet:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook -i inventory.yml storage-service.yml \
    -e "am_version=${AM_VERSION}" \
    --skip-tags amsrc-remote-pipeline \
    -v
```

## Installing the pipeline

Run the pipeline playbook. It registers the pipeline in the Storage Service:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook -i inventory.yml pipeline.yml \
    -e "am_version=${AM_VERSION}" \
    -v
```

## Connecting the Storage Service to the pipeline

Run the tasks of the Storage Service playbook that were skipped before:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook -i inventory.yml storage-service.yml \
    -e "am_version=${AM_VERSION}" \
    --tags amsrc-remote-pipeline \
    -v
```

They authorize the SSH key of the Storage Service in the pipeline host,
create the pipeline local filesystem space and move the currently processing
and transfer backlog locations of the pipeline to that space.

## Testing the installation

Check the Archivematica and Storage Service APIs:

```shell
../common/check-archivematica-apis
```

Check that the Storage Service reaches the currently processing and transfer
backlog locations through the pipeline local filesystem space:

```shell
./check-pipeline-space
```

Read the number of MCPClient instances from the inventory:

```shell
MCPCLIENT_INSTANCES=$(
    ansible-inventory -i inventory.yml --host pipeline \
        | jq '.archivematica_src_am_mcpclient_instances'
)
```

Check that the MCPClient instances are running and have workers registered
in Gearman. The output includes the processor time each instance has used:

```shell
./check-mcpclient-instances "$MCPCLIENT_INSTANCES"
```

## Testing the transfers

MCPServer processes as many packages at once as there are MCPClient
instances. Start a transfer for each instance from the sample data of the
Storage Service host:

```shell
TRANSFER_UUIDS=()
for ((instance = 1; instance <= MCPCLIENT_INSTANCES; instance++)); do
    TRANSFER_UUIDS+=("$(./start-transfer "multinode-test-${instance}")")
done
```

Wait for the transfers and resulting SIPs to finish:

```shell
for transfer_uuid in "${TRANSFER_UUIDS[@]}"; do
    ../common/wait-for-archivematica-transfer "$transfer_uuid"
done
```

Check that the Storage Service host stores the AIPs and that their fixity
checks pass:

```shell
for transfer_uuid in "${TRANSFER_UUIDS[@]}"; do
    ./check-stored-aip "$transfer_uuid"
done
```

Check the MCPClient instances again. They must still be running, and the
processor time they have used shows which of them processed the transfers:

```shell
./check-mcpclient-instances "$MCPCLIENT_INSTANCES"
```

Check that every job of the transfers and of their SIPs completed.
Archivematica reports a transfer or a SIP as complete even when some of its
jobs failed, for example when a normalization command fails:

```shell
for transfer_uuid in "${TRANSFER_UUIDS[@]}"; do
    ./check-jobs "$transfer_uuid"
done
```

## Inspecting the hosts

Open a shell on a host:

```shell
podman-compose exec --user root pipeline bash
podman-compose exec --user root storage-service bash
```

Collect the container, journal and application logs of both hosts:

```shell
../common/collect-test-logs logs pipeline storage-service
```

## Removing the Compose environment

```shell
podman-compose down
```

Remove the environment before testing another version or operating system,
because the hosts keep what the previous installation left.
