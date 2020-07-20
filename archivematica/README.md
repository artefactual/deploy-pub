<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Archivematica Installation](#archivematica-installation)
  - [A. Vagrant install](#a-vagrant-install)
    - [Requirements](#requirements)
    - [How to use](#how-to-use)
  - [B. VPS (remote server) install, running ansible from the local computer](#b-vps-remote-server-install-running-ansible-from-the-local-computer)
  - [C. VPS (remote server) install, running ansible from the remote server](#c-vps-remote-server-install-running-ansible-from-the-remote-server)
    - [Provision an ubuntu-xenial server](#provision-an-ubuntu-xenial-server)
    - [Enable the server firewall](#enable-the-server-firewall)
    - [Install Ansible](#install-ansible)
    - [Configure Ansible](#configure-ansible)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Archivematica Installation

The directories contain example playbooks and other required configuration files to
deploy Archivematica. In the sections below we provide examples on 
different ways these can be used:

- A. Vagrant install (deploy on a virtual machine in your local computer)
- B. VPS (remote server) install, running ansible from the local computer
- C. VPS (remote server) install, running ansible from the remote server


## A. Vagrant install

The provided playbook installs Archivematica on a local vagrant virtual
machine.

### Requirements

The following software needs to be installed in the local computer:

- Vagrant 1.9.2 or newer
- Ansible 2.2 or newer
- git

### How to use

0. Clone this git repository, and change the working directory according
   to the desired distribution (here we will use ubuntu 18.04)
    ```
    $ git clone https://github.com/artefactual/deploy-pub.git
    $ cd deploy-pub/archivematica/archivematica-ubuntu-18.04
    ```

1. By default, the ansible playbook will provision using the
   latest stable branches of archivematica, according to the file
   specified in the `include_vars` line in the file `singlenode.yml`
   (e.g., `vars-singlenode-1.11.yml` to deploy AM 1.11).
   To change the version to be deployed, change this configuration
   setting appropriately (e.g., to `vars-singlenode-qa.yml`, 
   `vars-singlenode-1.10.yml`). It is also possible to create a custom
    vars file and pass it instead (to modify role variables to deploy
    custom branches, etc.)  

2. Download the Ansible roles:
    ```
    $ ansible-galaxy install -f -p roles/ -r requirements.yml
    ```

3. Create the virtual machine and provision it:
    ```
    $ vagrant up
    ```
   After provisioning ends, Achivematica UI should be accessible at http://xxx.xxx.xxx.xxx and the Storage Service UI at http://xxx.xxx.xxx.xxx:8000 where xxx.xxx.xxx.xxx is the IP address specified in the `ip` variable of the Vagrantfile

4. To ssh to the VM, run:
    ```
    $ vagrant ssh
    ```

5. If you want to forward your SSH agent too, run:
    ```
    $ vagrant ssh -- -A
    ```

6. To (re-)provision the VM, run:
    * Using vagrant:
        ```
        $ vagrant provision
        ```
    * Using vagrant and custom ANSIBLE_ARGS. Use colons (:) to separate multiple parameters. For example to pass a tag to install Storage Service only, and verbose flag:
        ```
        $ ANSIBLE_ARGS="--tags=amsrc-ss:-vvv" vagrant provision
        ```
      Note that it is not possible to pass the (--extra-vars to ansible using the above, because extra_vars is reassigned in the Vagrantfile)
    * Using ansible commands directly (this allows you to pass ansible-specific parameters,
      such as tags and the verbose flag; remember to use extra-vars to pass the variables in the Vagrantfile ):
        ```
        $ ansible-playbook -i .vagrant/provisioners/ansible/inventory/vagrant_ansible_inventory singlenode.yml \
           -u vagrant \
           --private-key .vagrant/machines/am-local/virtualbox/private_key \
           --extra-vars="archivematica_src_dir=/vagrant/src archivematica_src_environment_type=development" \
           --tags="amsrc-pipeline-instcode" \
           -v
        ```

7. If you get errors regarding the Vagrant shared folders, they are usually due
to different versions of VirtualBox. One way to fix it is using a vagrant
plugin that installs the host's VirtualBox Guest Additions on the guest system:
    ```
    $ vagrant plugin install vagrant-vbguest
    $ vagrant vbguest
    ```


## B. VPS (remote server) install, running ansible from the local computer

This section describes how to deploy Archivematica to a remote server
(i.e., virtual private server, VPS), such as an AWS EC2 instance, OVH server or a Digital Ocean
Droplet.  It assumes that you have basic proficiency with the Unix command-line
and that you have the following installed:

- git
- Python
- [Ansible](http://docs.ansible.com/ansible/intro_installation.html) version 2.3

For this tutorial, we'll assuming that you have a [DigitalOcean account](https://www.digitalocean.com/community/tutorials/how-to-create-your-first-digitalocean-droplet-virtual-server) and that you have
created a new droplet. Other VPS providers should work similarily.

Note that Ubuntu 18.04 only includes Python 3 by default. You will need to install Python 2.7 after you set up your server, by logging in and issuing an `apt install python-minimal` command.

1. Clone the git repository that contains the Ansible configuration files which
   will be used to install Archivematica and all of its dependencies onto the
   system::

    $ git clone https://github.com/artefactual/deploy-pub.git

2. Download the Ansible roles that will install Archivematica and its
   dependencies::

    $ cd deploy-pub/playbooks/archivematica-bionic
    $ ansible-galaxy install -f -p roles/ -r requirements.yml

3. Create a ``hosts`` file to tell Ansible the alias for our server (``am-local``),
   its IP address and that we want to use the root user (where
   ``xxx.xxx.xxx.xxx`` is the droplet's actual IP)::

    $ echo "am-local ansible_host=xxx.xxx.xxx.xxx ansible_user=root" > hosts

4. Modify the Ansible config file ``ansible.cfg`` to point to our ``hosts`` file::

    $ cat ansible.cfg
    [defaults]
    nocows = 1
    inventory = hosts

5. If you do not have a SSH key, create one now (accepting the defaults)::

    $ ssh-keygen -t rsa

6. Copy the output of the above command to your clipboard and add it to the
   server's allowed hosts. For Digital Ocean, save it to your Droplet in the
   ["New SSH Key" web interface](https://cloud.digitalocean.com/settings/security)::

    $ cat ~/.ssh/id_rsa.pub

7. Use Ansible to create a new user on our server. Create a file (an Ansible
   playbook) called ``user.yml`` which has the content indicated by
   the output of ``cat`` below::

    ```yaml
    $ cat user.yml
    ---
    - name: create artefactual user
      hosts: am-local
      tasks:

        - name: add artefactual user
          user: name=artefactual shell=/bin/bash

        - name: add ssh keys to the corresponding user
          authorized_key: user=artefactual
                          key="{{ lookup('file', '~/.ssh/id_rsa.pub') }}"

        - name: configure passwordless sudo for the artefactual user
          lineinfile: dest=/etc/sudoers
                      state=present
                      regexp='^artefactual ALL\='
                      line='artefactual ALL=(ALL) NOPASSWD:ALL'
                      validate='/usr/sbin/visudo -cf %s'
    ```

The ``user.yml`` file creates a user called "artefactual" on the droplet, adds
your public key (assumed to be in ``~/.ssh/id_rsa.pub``) to the droplet, and
allows the artefactual user to run commands using ``sudo`` without a password.
Choose a different username than "artefactual" if you want.

To run the user playbook, use the command:
  
  ```
  $ ansible-playbook user.yml
  ```

8. Modify the ``hosts`` file to use the appropriate (e.g., ``artefactual``) user::

    ```bash
    $ cat hosts
    am-local ansible_host=xxx.xxx.xxx.xxx ansible_user=artefactual
    ```

9. Confirm that you can access the Digital Ocean droplet via SSH::

    `$ ssh artefactual@xxx.xxx.xxx.xxx`

10. And via Ansible::

    ```bash
    $ ansible am-local -m ping
    am-local | SUCCESS => {
        "changed": false,
        "ping": "pong"
    }
    ```

11. Install and deploy Archivematica and its dependencies::

    `$ ansible-playbook singlenode.yml`

The above command will take several minutes. If successful, the final output
should indicate ``unreachable=0 failed=0``.

Note: the ``ansible-playbook singlenode.yml`` command may fail initially. If it
does, try it again.

12. Confirm that Archivematica and its dependencies are installed and working
    by navigating to your Digital Ocean droplet's IP address
    (http://xxx.xxx.xxx.xxx). The Archivematica Storage Service should be being
    served at the same IP on port 8000, i.e., http://xxx.xxx.xxx.xxx:8000.

The default username and password for accessing the Storage Service are "admin"
and "archivematica".

You can test that your Archivematica installation works by performing a sample
Transfer and Ingest.


## C. VPS (remote server) install, running ansible from the remote server

This can be useful, for example when you can't (or don't want to) install
ansible on you local PC to deploy on a remote server (e.g., the local
computer is a Windows machine with only a minimal ssh application).

These instructions assume that you have basic knowledge of Unix commands, [SSH keys](https://help.ubuntu.com/community/SSH/OpenSSH/Keys), and that you have an OVH (or similar) account.

### Provision an ubuntu-xenial server
Login to your OVH account and provision a new Ubuntu 16.04 (Xenial) server.

These instructions assume that you are working as a sudo user called 'ubuntu'. OVH creates this account automatically when provisioning
Ubuntu servers.

These instructions also assume you are able to run passwordless instructions on your server which requires that your local
machine's public SSH key is added to the server. XX.XX.X.XXX is a stand-in for the actual IP address of your newly provisioned OVH server.

```
ssh@XX.XX.X.XXX
```

```
ubuntu@ovh-install-example:~$ cat >> .ssh/authorized_keys [your public key here]
```

Double-check that you are running Ubuntu 16.04

```
$ lsb_release -a
```

Check that git is installed

```
git --version
```

### Enable the server firewall
Follow good security practice by closing unused ports.

```
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

### Install Ansible
These instructions make use of Ansible playbooks which are like recipes for system administration tasks. Rather than having to run each
step manually, Ansible will run them in a prescribed order. This makes provisioning new systems much quicker and less error-prone.

* [Install Ansible using apt](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html#latest-releases-via-apt-ubuntu).

* Check that the Ansible installation switched your Python version from the default 3 to the required version 2.7.
    ```
    $ python -V
    ```

* Clone the git repository that contains the Ansible configuration files which will be used to install Archivematica and all of its
dependencies onto the OVH server:
    ```
    $ git clone https://github.com/artefactual/deploy-pub.git
    ```

### Configure Ansible
* Install the Ansible roles that will deploy Archivematica and its dependencies::
    ```
    $ cd deploy-pub/archivematica/archivematica-16.04
    ansible-galaxy install -f -p roles/ -r requirements.yml
    ```
*  Create a ```hosts``` file in this directory that tells Ansible how to connect to the target host. This Ansible playbook refers to the target host as 'am-local' so we use this name here. Also the target host is the same host we are using to run Ansible therefore we use the local host IP 127.0.0.1. The ansible user is the same user we use for login on this OVH server.

    ```
    $ cat hosts
    am-local ansible_host=127.0.0.1 ansible_user=ubuntu
    ```

 * Confirm that Ansible can connect to its target

    ```
    ~/deploy-pub/archivematica/archivematica-ubuntu-16.04$ ansible -i hosts am-local -m ping --connection=local
    ```

   results in:

    ```
    am-local | SUCCESS => {
        "changed": false,
        "ping": "pong"
    }
    ```

### Install Archivematica and its dependencies

  ```
  ~/deploy-pub/archivematica/archivematica-16.04$ ansible-playbook -i hosts singlenode.yml --connection=local
  ```

The `singlenode.yml` playbook setting `include_vars: “vars-singlenode-1.11.yml”` will ensure that the latest stable 1.11.x
branch of Archivematica and matching stable branch of the Storage Service branch are deployed.

The command above will take several minutes to run. Your shell session should be displaying the installation tasks as they are completed. If successful, the final output should read ```unreachable=0 failed=0```.

### Test Archivematica

* Confirm that Archivematica and its dependencies are installed and working by navigating your browser to your VM IP address (http://XX.XX.X.XXX).
* The Archivematica Storage Service should be served at the same IP address on port 8000 (http://XX.XX.X.XXX:8000).
* The username and password for accessing Archivematica and the Storage Service are specified in the `vars-singlenode-{version}.yml` file used
* Test that your Archivematica installation works by performing a sample Transfer and Ingest.
