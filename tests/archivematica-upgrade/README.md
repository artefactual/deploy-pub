# Archivematica playbook upgrade test

## Software requirements

- Podman
- Python 3
- curl

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

When using the `rockylinux:8` image, pin Ansible Core to 2.16.x:

```shell
python3 -m pip install -r requirements.txt \
    -c ../common/constraints-rocky8.txt
```

## Starting the Compose environment

Copy your SSH public key as the `ssh_pub_key` file next to the Compose file:

```shell
cp $HOME/.ssh/id_rsa.pub ssh_pub_key
```

The container defaults to Ubuntu 22.04. Set `DOCKER_IMAGE_NAME` and
`DOCKER_IMAGE_TAG` to select another tested environment:

```shell
export DOCKER_IMAGE_NAME=ubuntu
export DOCKER_IMAGE_TAG=22.04
```

Start the Compose services:

```shell
podman-compose up --detach
```

## Installing the stable version of Archivematica

Install the requirements of the stable version:

```shell
../common/prepare-ansible-roles \
    ../../playbooks/archivematica-noble/requirements.yml
```

Run the Archivematica installation playbook passing the stable version as the
`am_version` variable and the proper URLs for the Compose environment:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_REMOTE_PORT=2222
ansible-playbook -i localhost, playbook.yml \
    -u ubuntu \
    -e "am_version=1.18" \
    -e "archivematica_src_configure_am_site_url=http://archivematica" \
    -e "archivematica_src_configure_ss_url=http://archivematica:8000" \
    -v
```

## Testing the stable version of Archivematica

Get the Archivematica stable version:

```shell
curl \
    --silent \
    --dump-header - \
    --header "Authorization: ApiKey admin:this_is_the_am_api_key" \
    http://localhost:8000/api/processing-configuration/ | grep X-Archivematica-Version
```

Check the Archivematica and Storage Service APIs:

```shell
../common/check-archivematica-apis
```

## Upgrading to the QA version of Archivematica

Delete the requirements directory used for the stable version:

```shell
rm -rf roles
```

Install the requirements of the QA version:

```shell
../common/prepare-ansible-roles \
    ../../playbooks/archivematica-noble/requirements-qa.yml
```

Run the Archivematica installation playbook passing the QA version as the
`am_version` variable, the proper URLs for the Compose environment and
the tag to upgrade installations:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_REMOTE_PORT=2222
ansible-playbook -i localhost, playbook.yml \
    -u ubuntu \
    -e "am_version=qa" \
    -e "archivematica_src_configure_am_site_url=http://archivematica" \
    -e "archivematica_src_configure_ss_url=http://archivematica:8000" \
    -e "elasticsearch_version=8.19.2" \
    -t "elasticsearch,archivematica-src" \
    -v
```

## Testing the QA version of Archivematica

Get the Archivematica QA version:

```shell
curl \
    --silent \
    --dump-header - \
    --header "Authorization: ApiKey admin:this_is_the_am_api_key" \
    http://localhost:8000/api/processing-configuration/ | grep X-Archivematica-Version
```

Check the Archivematica and Storage Service APIs:

```shell
../common/check-archivematica-apis
```
