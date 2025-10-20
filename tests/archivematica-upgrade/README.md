# Archivematica playbook upgrade test

## Software requirements

- Podman
- crun >= 1.14.4
- Python 3
- curl

## Installing Ansible

Create a virtual environment and activate it:

```shell
python3 -m venv .venv
source .venv/bin/activate
```

Install the Python requirements (these versions are compatible with
symbolic links which are used in the the artefactual-atom role):

```shell
python3 -m pip install -r requirements.txt
```

## Starting the Compose environment

Copy your SSH public key as the `ssh_pub_key` file next to the `Dockerfile`:

```shell
cp $HOME/.ssh/id_rsa.pub ssh_pub_key
```

Start the Compose services:

```shell
podman-compose up --detach
```

## Installing the stable version of Archivematica

Install the requirements of the stable version:

```shell
ansible-galaxy install -f -p roles/ -r ../../playbooks/archivematica-noble/requirements.yml
```

Run the Archivematica installation playbook passing the stable version as the
`am_version` variable and the proper URLs for the Compose environment:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_REMOTE_PORT=2222
ansible-playbook -i localhost, playbook.yml \
    -u ubuntu \
    -e "am_version=1.16" \
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

Call an Archivematica API endpoint:

```shell
curl --header "Authorization: ApiKey admin:this_is_the_am_api_key" http://localhost:8000/api/processing-configuration/
```

Call a Storage Service API endpoint:

```shell
curl --header "Authorization: ApiKey admin:this_is_the_ss_api_key" http://localhost:8001/api/v2/pipeline/
```

## Upgrading to the QA version of Archivematica

Uninstall Elasticsearch 6.x:

```shell
podman-compose exec --user root archivematica bash -c "apt-get purge -y elasticsearch"
podman-compose exec --user root archivematica bash -c "rm -rf /etc/elasticsearch/ /var/lib/elasticsearch /var/log/elasticsearch"
```

Delete the requirements directory used for the stable version:

```shell
rm -rf roles
```

Install the requirements of the QA version:

```shell
ansible-galaxy install -f -p roles/ -r ../../playbooks/archivematica-noble/requirements-qa.yml
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

Call an Archivematica API endpoint:

```shell
curl --header "Authorization: ApiKey admin:this_is_the_am_api_key" http://localhost:8000/api/processing-configuration/
```

Call a Storage Service API endpoint:

```shell
curl --header "Authorization: ApiKey admin:this_is_the_ss_api_key" http://localhost:8001/api/v2/pipeline/
```
