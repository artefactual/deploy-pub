# Archivematica playbook

The provided playbook installs Archivematica on a local vagrant virtual
machine.

## Requirements

- Vagrant 1.9 or newer
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
