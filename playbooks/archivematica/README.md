# Archivematica playbook

The provided playbook installs Archivematica on a local vagrant virtual
machine. For instructions on using deploy-pub to install Archivematica on a
Digital Ocean droplet, see the [Digital Ocean Droplet
Deploy](docs/digital-ocean-install-example.rst) document.

## Requirements

- Vagrant 1.7 or newer
- Ansible 2.1.2 or newer

## How to use

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

6. The ansible playbook `singlenode-1.6.yml` specified in the Vagrantfile will provision using stable/1.6.x and stable/0.10.x branches of Archivematica and Storage Service. To provision using the qa 1.x/0.x branches, replace `singlenode-1.6.yml` with `singlenode-qa.yml`.

For more archivematica development information, see: https://wiki.archivematica.org/Getting_started
