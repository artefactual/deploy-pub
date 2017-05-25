# Archivematica playbook

The provided playbook installs Archivematica on a local vagrant virtual
machine. For instructions on using deploy-pub to install Archivematica on a
Digital Ocean droplet, see the [Digital Ocean Droplet
Deploy](docs/digital-ocean-install-example.rst) document.

## Requirements

- Vagrant 1.7 or newer
- Ansible 2.2 or newer

## How to use

1. Download the Ansible roles:
  ```
  $ ansible-galaxy install -f -p roles/ -r requirements.yml
  ```

2. Create the virtual machine and provision it:
  ```
  $ vagrant up
  ```
  After provisioning ends, Achivematica UI should be accessible at http://xxx.xxx.xxx.xxx and the Storage Service UI at http://xxx.xxx.xxx.xxx:8000 where xxx.xxx.xxx.xxx is the IP address specified in the `ip` variable of the Vagrantfile

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
        $ ANSIBLE_ARGS="--tags=amsrc-ss:-vvv" vagrant provision       (in bash)
        $ env ANSIBLE_ARGS="--tags=amsrc-ss:-vvv" vagrant provision   (in fish)
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

6. The ansible playbook `singlenode.yml` specified in the Vagrantfile will provision using the branches of archivematica specfied in the file `vars-singlenode.yml`. Edit this file if need to deploy other branches.  


For more archivematica development information, see: https://wiki.archivematica.org/Getting_started
