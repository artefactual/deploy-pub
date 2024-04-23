# DIP upload test

## Software requirements

- Vagrant 2.4.1 (with vagrant-vbguest plugin)
- VirtualBox 7.0
- Python 3
- curl

## Tested Vagrant boxes

This playbook has been tested with Vagrant 2.4.1 and VirtualBox 7.0.14 r161095
using any of the following Vagrant boxes and versions:

- Archivematica: ubuntu/jammy64 (v20240403.0.0)
- AtoM: ubuntu/focal64 (v20231003.0.0)

## Installing Ansible

Create a virtual environment and activate it:

```shell
python3 -m venv .venv
source .venv/bin/activate
```

Install `ansible` and `ansible-core` (these versions are compatible with
symbolic links which are used in the the artefactual-atom role):

```shell
python3 -m pip install ansible==8.5.0 ansible-core==2.15.5
```

Install the playbook requirements:

```shell
ansible-galaxy install -f -p roles/ -r requirements.yml
```

## Setting up VirtualBox

Install the `vagrant-vbguest` plugin:

```shell
vagrant plugin install vagrant-vbguest
```

Add the VMs IP network to the VirtualBox networks file:

```shell
sudo mkdir -p /etc/vbox/
echo "* 192.168.33.0/24" | sudo tee -a /etc/vbox/networks.conf
```

## Provisioning the Archivematica VM

Start the VM passing the `VAGRANT_BOX` environment variable with the ID of the
Ubuntu 22.04 Vagrant Cloud:

```shell
env VAGRANT_BOX=ubuntu/jammy64 vagrant up archivematica
```

Run the Archivematica installation playbook:

```shell
ansible-playbook -i 192.168.33.2, archivematica.yml \
    -u vagrant \
    --private-key $PWD/.vagrant/machines/archivematica/virtualbox/private_key \
    -v
```

Add the `vagrant` user to the `archivematica` group so it can copy AIPs
from the shared directory:

```shell
vagrant ssh archivematica -c 'sudo usermod -a -G archivematica vagrant'
```

Get the SSH public key of the `archivematica` user so we can use it when
provisioning the AtoM VM:

```shell
AM_SSH_PUB_KEY=$(vagrant ssh archivematica -c 'sudo cat /var/lib/archivematica/.ssh/id_rsa.pub')
```

## Provisioning the AtoM VM

Start the VM passing the `VAGRANT_BOX` environment variable with the ID of the
Ubuntu 20.04 Vagrant Cloud:

```shell
env VAGRANT_BOX=ubuntu/focal64 vagrant up atom
```

Run the AtoM installation playbook passing the `archivematica_ssh_pub_key`
variable with the contents of `$AM_SSH_PUB_KEY`:

```shell
ansible-playbook -i 192.168.33.3, atom.yml \
    -u vagrant \
    --private-key $PWD/.vagrant/machines/atom/virtualbox/private_key \
    -e "archivematica_ssh_pub_key='$AM_SSH_PUB_KEY'" \
    -v
```

## Testing the Archivematica installation

Call an Archivematica API endpoint:

```shell
curl --header "Authorization: ApiKey admin:this_is_the_am_api_key" http://192.168.33.2/api/processing-configuration/
```

Call a Storage Service API endpoint:

```shell
curl --header "Authorization: ApiKey admin:this_is_the_ss_api_key" http://192.168.33.2:8000/api/v2/pipeline/
```

## Testing the AtoM installation

Call an AtoM API endpoint:

```shell
curl --header "REST-API-Key: this_is_the_atom_dip_upload_api_key" http://192.168.33.3/index.php/api/informationobjects
```

## Testing DIP upload

Create a processing configuration for DIP upload:

```shell
vagrant ssh archivematica -c "sudo -u archivematica cp /var/archivematica/sharedDirectory/sharedMicroServiceTasksConfigs/processingMCPConfigs/{automated,dipupload}ProcessingMCP.xml"
```

Update the DIP upload processing configuration:

```shell
# Change 'Normalize for preservation' to 'Normalize for preservation and access'
vagrant ssh archivematica -c "sudo -u archivematica sed --in-place 's|612e3609-ce9a-4df6-a9a3-63d634d2d934|b93cecd4-71f2-4e28-bc39-d32fd62c5a94|g' /var/archivematica/sharedDirectory/sharedMicroServiceTasksConfigs/processingMCPConfigs/dipuploadProcessingMCP.xml"
# Change 'Do not upload DIP' to 'Upload DIP to AtoM/Binder'
vagrant ssh archivematica -c "sudo -u archivematica sed --in-place 's|6eb8ebe7-fab3-4e4c-b9d7-14de17625baa|0fe9842f-9519-4067-a691-8a363132ae24|g' /var/archivematica/sharedDirectory/sharedMicroServiceTasksConfigs/processingMCPConfigs/dipuploadProcessingMCP.xml"
```

Import Atom sample data:

```shell
vagrant ssh atom -c "cd /usr/share/nginx/atom/ && sudo -u www-data php -d memory_limit=-1 symfony csv:import /usr/share/nginx/atom/lib/task/import/example/isad/example_information_objects_isad.csv"
vagrant ssh atom -c "cd /usr/share/nginx/atom/ && sudo -u www-data php -d memory_limit=-1 symfony propel:build-nested-set"
vagrant ssh atom -c "cd /usr/share/nginx/atom/ && sudo -u www-data php -d memory_limit=-1 symfony cc"
vagrant ssh atom -c "cd /usr/share/nginx/atom/ && sudo -u www-data php -d memory_limit=-1 symfony search:populate"
```

Start a transfer and upload the DIP to the sample archival description:

```shell
curl \
    --header "Authorization: ApiKey admin:this_is_the_am_api_key" \
    --request POST \
    --data "{ \
        \"name\": \"dip-upload-test\", \
        \"path\": \"$(echo -n '/home/vagrant/archivematica-sampledata/SampleTransfers/DemoTransferCSV' | base64 -w 0)\", \
        \"type\": \"standard\", \
        \"processing_config\": \"dipupload\", \
        \"access_system_id\": \"example-item\" \
    }" \
    http://192.168.33.2/api/v2beta/package
```

Wait for the transfer to finish:

```shell
sleep 120
```

Verify a digital object was uploaded and attached to the sample archival description:

```shell
curl \
    --header "REST-API-Key: this_is_the_atom_dip_upload_api_key" \
    --silent \
    http://192.168.33.3/index.php/api/informationobjects/beihai-guanxi-china-1988 | python3 -m json.tool | grep '"parent": "example-item"'
```
