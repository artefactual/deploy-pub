How to Deploy Archivematica to a Digital Ocean Droplet
================================================================================

This document describes how to deploy Archivematica to a Digital Ocean droplet
(i.e., virtual private server, VPS).  It assumes that you have basic
proficiency with the Unix command-line and that you have the following
installed.

- git
- Python
- Ansible (http://docs.ansible.com/ansible/intro_installation.html)

We are also assuming that you have a Digital Ocean account and that you have
created a new droplet. The following URL may be useful for accomplishing this.

- https://www.digitalocean.com/community/tutorials/how-to-create-your-first-digitalocean-droplet-virtual-server

In this example, we are using Ubuntu 14.04.


1. Clone the git repository that contains the Ansible configuration files which
   will be used to install Archivematica and all of its dependencies onto the
   Digital Ocean droplet::

    $ git clone https://github.com/artefactual/deploy-pub.git

2. Download the Ansible roles that will install Archivematica and its
   dependencies::

    $ cd deploy-pub/playbooks/archivematica
    $ ansible-galaxy install -f -p roles/ -r requirements.yml

3. Create a `hosts` file to tell Ansible the alias for our droplet (`am-do`),
   its IP address and that we want to use the root user (where
   `xxx.xxx.xxx.xxx` is the droplet's actual IP)::

    $ cat hosts
    am-do ansible_host=xxx.xxx.xxx.xxx ansible_user=root

4. Modify the Ansible config file `ansible.cfg` to point to our `hosts` file::

    $ cat ansible.cfg
    [defaults]
    nocows = 1
    inventory = hosts

5. If you do not have a SSH key, create one now (accepting the defaults)::

    $ ssh-keygen -t rsa

6. Copy the output of the above command to your clipboard and save it to your
   digital ocean droplet in the "New SSH Key" web interface (see
   https://cloud.digitalocean.com/settings/security)::

    $ cat ~/.ssh/id_rsa.pub

7. Use Ansible to create a new user on our Digital Ocean droplet. Create a file
   (an Ansible playbook) called `user.yml` which has the content indicated by
   the output of `cat` below::

    $ cat user.yml
    ---
    - name: create artefactual user
      hosts: am-do
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

The `user.yml` file creates a user called "artefactual" on the droplet, adds
your public key (assumed to be in `~/.ssh/id_rsa.pub`) to the droplet, and
allows the artefactual user to run commands using `sudo` without a password.
Choose a different username than "artefactual" if you want.

8. Modify the `hosts` file to use the appropriate (e.g., `artefactual`) user::

    $ cat hosts
    am-do ansible_host=xxx.xxx.xxx.xxx ansible_user=artefactual


9. Confirm that you can access the Digital Ocean droplet via SSH::

    $ ssh artefactual@xxx.xxx.xxx.xxx

10. And via Ansible::

    $ ansible am-do -m ping
    am-do | SUCCESS => {
        "changed": false, 
        "ping": "pong"
    }

11. If desired, alter the value of the `archivematica_src_ss_version` variable
    in `deploy-pub/playbooks/archivematica/vars-singlenode.yml` so that
    instead of "qa/1.x" it valuates to another Archivematica branch, e.g.,
    "dev/issue-9213-1.5-integration".

12. Install and deploy Archivematica and its dependencies::

    $ ansible-playbook singlenode.yml

The above command will take several minutes. If successful, the final output
should indicate `unreachable=0 failed=0`.

Note: the `ansible-playbook singlenode.yml` command may fail initially. If it
does, try it again.

13. Confirm that Archivematica and its dependencies are installed and working
    by navigating to your Digital Ocean droplet's IP address
    (http://xxx.xxx.xxx.xxx). The Archivematica Storage Service should be being
    served at the same IP on port 8000, i.e., http://xxx.xxx.xxx.xxx:8000.

The default username and password for accessing the Storage Service are "test"
and "test". Once you log in, go to the "Administration" tab, then click "Users"
on the lefthand column, then click the "Edit" button of the "test" user, then
copy the API key at the bottom of the page to your clipboard.

Then navigate to the Archivematica dashboard (http://xxx.xxx.xxx.xxx), fill in
the form, and click "Create". When communication with the FPR Server has
completed, click the "continue" button. Now enter the API key that you copied
from the Storage Service and click the first button, the one labelled "Register
with the storage service & use default configuration."

You can test that your Archivematica installation works by performing a sample
Transfer and Ingest.


