# DIP upload test

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

Install the playbook requirements:

```shell
ansible-galaxy install -f -p roles/ -r requirements.yml
```

## Starting the Compose environment

Copy your SSH public key as the `ssh_pub_key` file next to the `Containerfile`:

```shell
cp $HOME/.ssh/id_rsa.pub ssh_pub_key
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
ansible-playbook -i localhost, archivematica.yml \
    -u ubuntu \
    -v
```

Add the `ubuntu` user to the `archivematica` group so it can copy AIPs
from the shared directory:

```shell
podman-compose exec --user root archivematica usermod -a -G archivematica ubuntu
```

Get the SSH public key of the `archivematica` user so we can use it when
installing AtoM:

```shell
AM_SSH_PUB_KEY=$(podman-compose exec --user archivematica archivematica cat /var/lib/archivematica/.ssh/id_rsa.pub)
```

## Installing AtoM

Run the AtoM installation playbook passing the `archivematica_ssh_pub_key`
variable with the contents of `$AM_SSH_PUB_KEY`:

```shell
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_REMOTE_PORT=9222
ansible-playbook -i localhost, atom.yml \
    -u ubuntu \
    -e "archivematica_ssh_pub_key='$AM_SSH_PUB_KEY'" \
    -v
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

## Testing the AtoM installation

Call an AtoM API endpoint:

```shell
curl --header "REST-API-Key: this_is_the_atom_dip_upload_api_key" http://localhost:9000/index.php/api/informationobjects
```

## Testing DIP upload

Create a processing configuration for DIP upload:

```shell
podman-compose exec --user archivematica archivematica cp /var/archivematica/sharedDirectory/sharedMicroServiceTasksConfigs/processingMCPConfigs/automatedProcessingMCP.xml /var/archivematica/sharedDirectory/sharedMicroServiceTasksConfigs/processingMCPConfigs/dipuploadProcessingMCP.xml
```

Update the DIP upload processing configuration:

```shell
# Change 'Normalize for preservation' to 'Normalize for preservation and access'
podman-compose exec --user archivematica archivematica sed --in-place 's|612e3609-ce9a-4df6-a9a3-63d634d2d934|b93cecd4-71f2-4e28-bc39-d32fd62c5a94|g' /var/archivematica/sharedDirectory/sharedMicroServiceTasksConfigs/processingMCPConfigs/dipuploadProcessingMCP.xml
# Change 'Do not upload DIP' to 'Upload DIP to AtoM/Binder'
podman-compose exec --user archivematica archivematica sed --in-place 's|6eb8ebe7-fab3-4e4c-b9d7-14de17625baa|0fe9842f-9519-4067-a691-8a363132ae24|g' /var/archivematica/sharedDirectory/sharedMicroServiceTasksConfigs/processingMCPConfigs/dipuploadProcessingMCP.xml
```

Import the Atom sample data:

```shell
podman-compose exec --user www-data --workdir /usr/share/nginx/atom/ atom php -d memory_limit=-1 symfony csv:import /usr/share/nginx/atom/lib/task/import/example/isad/example_information_objects_isad.csv
podman-compose exec --user www-data --workdir /usr/share/nginx/atom/ atom php -d memory_limit=-1 symfony propel:build-nested-set
podman-compose exec --user www-data --workdir /usr/share/nginx/atom/ atom php -d memory_limit=-1 symfony cc
podman-compose exec --user www-data --workdir /usr/share/nginx/atom/ atom php -d memory_limit=-1 symfony search:populate
```

Start a transfer and upload the DIP to the sample archival description:

```shell
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
```

Wait for the transfer to finish:

```shell
sleep 120
```

Display the contents of the DIP:

```shell
podman-compose exec --user archivematica archivematica bash -c "find /var/archivematica/sharedDirectory/www/DIPsStore/ -name 'dip-upload-test-*' | xargs tree"
```

Verify a digital object was uploaded and attached to the sample archival description:

```shell
curl \
    --header "REST-API-Key: this_is_the_atom_dip_upload_api_key" \
    --silent \
    http://localhost:9000/index.php/api/informationobjects/beihai-guanxi-china-1988 | python3 -m json.tool | grep '"parent": "example-item"'
```
