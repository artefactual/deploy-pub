# Archivematica Acceptance Tests (AMAUATs)

## Software requirements

- Podman
- crun >= 1.15
- Python 3
- curl
- Latest Google Chrome with chromedriver or Firefox with geckodriver
- 7-Zip

## Tested Docker images

This playbook has been tested with Podman 3.4.4 and podman-compose 1.1.0
using any of the following Docker images and tags:

- rockylinux:9
- rockylinux:8
- ubuntu:24.04
- ubuntu:22.04

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

Install the playbook requirements:

```shell
ansible-galaxy install -f -p roles/ -r requirements.yml
```

## Starting the Compose environment

Copy your SSH public key as the `ssh_pub_key` file next to the `Dockerfile`:

```shell
cp $HOME/.ssh/id_rsa.pub ssh_pub_key
```

Set the Docker image and tag to use for the Compose services:

```shell
export DOCKER_IMAGE_NAME=ubuntu
export DOCKER_IMAGE_TAG=24.04
```

Start the Compose services:

```shell
podman-compose up --detach
```

## Installing Archivematica

Run the Archivematica installation playbook:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_REMOTE_PORT=2222
ansible-playbook -i localhost, playbook.yml \
    -u ubuntu \
    -v
```

Add the `ubuntu` user to the `archivematica` group so it can copy AIPs
from the shared directory:

```shell
podman-compose exec --user root archivematica usermod -a -G archivematica ubuntu
```

The AMAUATs expect the Archivematica sample data to be in the
`/home/archivematica` directory:

```shell
podman-compose exec --user root archivematica ln -s /home/ubuntu /home/archivematica
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
    -D home=ubuntu \
    -D server_user=ubuntu \
    -D transfer_source_path=/home/ubuntu/archivematica-sampledata/TestTransfers/acceptance-tests \
    -D ssh_identity_file=$HOME/.ssh/id_rsa
```

Some feature files (AIP encryption and UUIDs for directories) copy AIPs from
the remote host using `scp` but they assume port 22 is used for the SSH service.
You can set this in your `$HOME/.ssh/config` file to make them work with port
2222:

```console
Host localhost
    Port 2222
```
