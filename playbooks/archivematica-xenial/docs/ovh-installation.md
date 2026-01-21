# How to deploy Archivematica to an OVH server

[OVH.com](https://ovh.com) is a major cloud services provider like Amazon Web Services, Microsoft Azure, Rackspace or Digital Ocean.
OVH.com is often used by Artefactual Systems to host instances of Archivematica for clients. Below are instructions on how to install
Archivematica to your own OVH cloud server. These instructions should be very similar for most other cloud server providers.

These instructions assume that you have basic knowledge of Unix commands, [SSH keys](https://help.ubuntu.com/community/SSH/OpenSSH/Keys), and that you have an OVH (or similar) account.

## Provision an ubuntu-xenial server
Login to your OVH account and provision a new Ubuntu 16.04 (Xenial) server. The [minimum technical requirements](https://www.archivematica.org/en/docs/archivematica-1.7/admin-manual/installation-setup/installation/installation/#tech-requirements)
for an Archivematica installation is 2 CPU cores, 4GB memory and 200GB disk space.

These instructions assume that you are working as a sudo user called 'ubuntu'. OVH creates this account automatically when provisioning
Ubuntu servers.

These instructions also assume you are able to run passwordless instructions on your server which requires that your local
machine's public SSH key is added to the server. XX.XX.X.XXX is a stand-in for the actual IP address of your newly provisioned OVH server.

```ssh@XX.XX.X.XXX```

```ubuntu@ovh-install-example:~$ cat >> .ssh/authorized_keys [your public key here] ```

Double-check that you are running Ubuntu 16.04

```$ lsb_release -a```

Check that git is installed

```git --version```

## Enable the server firewall
Follow good security practice by closing unused ports.

```
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

## Install Ansible
These instructions make use of Ansible playbooks which are like recipes for system administration tasks. Rather than having to run each
step manually, Ansible will run them in a prescribed order. This makes provisioning new systems much quicker and less error-prone.

* [Install Ansible using apt](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html#latest-releases-via-apt-ubuntu).

* Check that the Ansible installation switched your Python version from the default 3 to the required version 2.7.

```python -V```

* Clone the git repository that contains the Ansible configuration files which will be used to install Archivematica and all of its
dependencies onto the OVH server::
```
git clone https://github.com/artefactual/deploy-pub.git
```

## Congifure Ansible
* Install the Ansible roles that will deploy Archivematica and its dependencies::
```
cd deploy-pub/playbooks/archivematica-xenial
ansible-galaxy install -f -p roles/ -r requirements.yml
```
*  Create a ```hosts``` file in this directory that tells Ansible how to connect to the target host. This Ansible playbook refers to the target host as 'am-local' so we use this name here. Also the target host is the same host we are using to run Ansible therefore we use the local host IP 127.0.0.1. The ansible user is the same user we use for login on this OVH server.

 ```
 cat hosts
 am-local ansible_host=127.0.0.1 ansible_user=ubuntu
 ```

 * Confirm that Ansible can connect to its target

 ```
 ~/deploy-pub/playbooks/archivematica-xenial$ ansible -i hosts am-local -m ping --connection=local
 ```
 results in:
 ```
am-local | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

## Install Archivematica and its dependencies
```
~/deploy-pub/playbooks/archivematica-xenial$ ansible-playbook -i hosts singlenode.yml --connection=local
```

The [singlenode.yml](https://github.com/artefactual/deploy-pub/blob/master/playbooks/archivematica-xenial/singlenode.yml) playbook setting ```include_vars: “vars-singlenode-1.7.yml”``` will ensure that the latest stable 1.7.x
branch of Archivematica and 0.11.x of the Storage Service branch are deployed.

The command above will take several minutes to run. Your shell session should be displaying the installation tasks as they are completed. If successful, the final output should read ```unreachable=0 failed=0```.

## Test Archivematica

* Confirm that Archivematica and its dependencies are installed and working by navigating your browser to your VM IP address (http://XX.XX.X.XXX).
* This should forward to the ```/installer/welcome``` address which you will use to configure your Archivematica installation. See the [Post Installation Configuration](https://www.archivematica.org/en/docs/archivematica-1.7/admin-manual/installation-setup/installation/install-ansible/#ansible-post-install-config) instructions used for all for all Archivematica installs.
* The Archivematica Storage Service should be served at the same IP address on port 8000 (http://XX.XX.X.XXX:8000).
* The default username and password for accessing the Storage Service are "test" and "test". Once you log in, go to the "Administration" tab, then click "Users" on the lefthand column, then click the "Edit" button for the "test" user, then copy the API key at the bottom of the page to your clipboard. This will be used to connect your newly installed Archivematica pipeline to this Storage Service.
* Now navigate to the Archivematica dashboard (http://XX.XX.X.XXX/installer/welcome, fill in the form, and click "Create".
* On the "Register this pipeline in the Storage Service" form enter API key that you copied from the Storage Service and click the "Register" button.
* Test that your Archivematica installation works by performing a sample Transfer and Ingest.
