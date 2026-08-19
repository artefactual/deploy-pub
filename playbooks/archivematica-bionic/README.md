# Archivematica Installation

## Vagrant install

The provided playbook installs Archivematica on a local vagrant virtual
machine.

### Requirements

- Vagrant 1.9 or newer
- Ansible 2.2 or newer

### How to use

1. Download the Ansible roles:
  ```
  $ ansible-galaxy install -f -p roles/ -r requirements.yml
  ```

2. Create the virtual machine and provision it:
  ```
  $ vagrant up
  ```

3. To ssh to the VM, run:
  ```
  $ vagrant ssh
  ```

4. If you want to forward your SSH agent too, run:
  ```
  $ vagrant ssh -- -A
  ```

5. To (re-)provision the VM, run:
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

6. The ansible playbook `singlenode.yml` specified in the Vagrantfile will provision using qa branches of archivematica. To provision using the stable 1.7.x/0.12.x branches, replace "vars-singlenode-qa.yml" with "vars-singlenode-1.7.yml" in `singlenode.yml`. You can also modify create a custom vars file and pass it instead (to modify role variables to deploy custom branches, etc.)  

7. If you get errors regarding the Vagrant shared folders, they are usually due
to different versions of VirtualBox. One way to fix it is using a vagrant
plugin that installs the host's VirtualBox Guest Additions on the guest system:
  ```
  $ vagrant plugin install vagrant-vbguest
  $ vagrant vbguest
  ```

# Login and credentials

If you are using the default values in vars-singlenode-XXXX.yml and Vagrantfile files, the login URLS are:

* Dashboard:       http://192.168.168.198
* Storage Service: http://192.168.168.198:8000

Credentials:

* user: admin
* password: archivematica

For more archivematica development information, see: https://wiki.archivematica.org/Getting_started

## VPS Install, or How to Deploy Archivematica to a Single Node

This section describes how to deploy Archivematica to a remote server
(i.e., virtual private server, VPS), such as an AWS EC2 instance or Digital Ocean
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
