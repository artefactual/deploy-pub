# AtoM Playbook

The provided playbook installs AtoM on a local Vagrant virtual machine.

## Requirements

- Vagrant 2.1.4 or newer
- Ansible 2.10 or newer

Tested with Ansible 2.15.6 and Vagrant 2.4.3-1

## How to use

Dowload the Ansible roles

    $ ansible-galaxy install -f -p roles/ -r requirements.yml

Create the virtual machine and provision it:

    $ vagrant up

To ssh to the VM, run:

    $ vagrant ssh

If you want to forward your SSH agent too, run:

    $ vagrant ssh -- -A

To (re-)provision the VM, using Vagrant:

    $ vagrant provision

To (re-)provision the VM, using Ansible commands directly:

    $ ansible-playbook singlenode.yml
        --inventory-file=".vagrant/provisioners/ansible/inventory/vagrant_ansible_inventory" \
        --user="vagrant" \
        --private-key=".vagrant/machines/atom-local/virtualbox/private_key" \
        --extra-vars="atom_dir=/vagrant/src atom_environment_type=development" \
        --verbose

To (re-)provision the VM, passing your own arguments to `Ansible`:

    $ ANSIBLE_ARGS="--tags=elasticsearch,percona,memcached,gearman,nginx" vagrant provision

You can access AtoM service: http://192.168.168.200 (user: demo@example.com, pass: demo)
