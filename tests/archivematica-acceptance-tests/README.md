# Archivematica Acceptance Tests (AMAUATs)

## Software requirements

- Vagrant 2.4.1 (with vagrant-vbguest plugin)
- VirtualBox 7.0
- Python 3
- Latest Google Chrome with chromedriver or Firefox with geckodriver

## Tested Vagrant boxes

This playbook has been tested with Vagrant 2.4.1 and VirtualBox 7.0.14 r161095
using any of the following Vagrant boxes and versions:

- rockylinux/9 (v3.0.0)
- rockylinux/8 (v9.0.0)
- almalinux/9 (v9.3.20231118)
- ubuntu/jammy64 (v20240403.0.0)

## Provisioning the VM

Install the `vagrant-vbguest` plugin:

```shell
vagrant plugin install vagrant-vbguest
```

Add the VM IP address to the VirtualBox networks file:

```shell
sudo mkdir -p /etc/vbox/
echo "* 192.168.33.0/24" | sudo tee -a /etc/vbox/networks.conf
```

Set the `VAGRANT_BOX` environment variable with the ID of a Vagrant Cloud
box. The `ubuntu/jammy64` box is used by default if `VAGRANT_BOX` is not set:

```shell
export VAGRANT_BOX=ubuntu/jammy64
```

Start the VM:

```shell
vagrant up
```

## Installing Archivematica

Create a virtual environment and activate it:

```shell
python3 -m venv .venv
source .venv/bin/activate
```

Install `ansible` and `behave`:

```shell
python3 -m pip install ansible behave
```

Install the playbook requirements:

```shell
ansible-galaxy install -f -p roles/ -r requirements.yml
```

Run the installation playbook:

```shell
ansible-playbook -i 192.168.33.2, playbook.yml \
    -u vagrant \
    --private-key $PWD/.vagrant/machines/default/virtualbox/private_key \
    -v
```

Add the `vagrant` user to the `archivematica` group so it can copy AIPs
from the shared directory:

```shell
vagrant ssh -c 'sudo usermod -a -G archivematica vagrant'
```

The AMAUATs expect the Archivematica sample data to be in the
`/home/archivematica` directory:

```shell
vagrant ssh -c 'sudo ln -s /home/vagrant /home/archivematica'
```

Clone the AMAUATs repository:

```shell
git clone https://github.com/artefactual-labs/archivematica-acceptance-tests
```

Install the AMAUATs requirements:

```shell
python3 -m pip install -r archivematica-acceptance-tests/requirements.txt
```

Run any [feature file](https://github.com/artefactual-labs/archivematica-acceptance-tests/tree/qa/1.x/features/black_box)
in the AMAUATs using its filename. This example shows how to run the
`create-aip.feature` file with `Chrome`.

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
    -D am_url=http://192.168.33.2/ \
    -D am_api_key="this_is_the_am_api_key" \
    -D ss_username=admin \
    -D ss_password=archivematica \
    -D ss_api_key="this_is_the_ss_api_key" \
    -D ss_url=http://192.168.33.2:8000/ \
    -D home=vagrant \
    -D server_user=vagrant \
    -D transfer_source_path=/home/vagrant/archivematica-sampledata/TestTransfers/acceptance-tests \
    -D ssh_identity_file=$PWD/.vagrant/machines/default/virtualbox/private_key
```
