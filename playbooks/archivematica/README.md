# Archivematica playbook

The provided playbook installs Archivematica on a local vagrant virtual
machine. For instructions on using deploy-pub to install Archivematica on a
Digital Ocean droplet, see the [Digital Ocean Droplet
Deploy](docs/digital-ocean-install-example.rst) document.

## Requirements

- Vagrant 1.7 or newer
- Ansible 2.1.2 or newer

If you are using Windows, note that symlinks are not created by default and this will cause the "vagrant provision" step to fail. To enable symlink creation, do one of the following:

- Run the following commands as a Windows Administrator; or
- Have a Windows Administrator add you to the "Create symbolic links" policy in the "Local Security Policy" (located under "Local Policies" then "User Rights Assignment") and then log out and log back in for the policy to take effect.

## How to use

1. Create the virtual machine and provision it:
  ```
  $ vagrant up
  ```

2. To ssh to the VM, run:
  ```
  $ vagrant ssh
  ```

3. If you want to forward your SSH agent too, run:
  ```
  $ vagrant ssh -- -A
  ```

4. To (re-)provision the VM, run:
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

5. The ansible playbook `singlenode.yml` specified in the Vagrantfile will provision using stable branches of archivematica. To provision using the qa 1.x/0.x branches, replace "vars-singlenode-1.6.yml" with "vars-singlenode-qa.yml" in `singlenode.yml`. You can also modify create a custom vars file and pass it instead (to modify role variables to deploy custom branches, etc.)  


For more archivematica development information, see: https://wiki.archivematica.org/Getting_started
