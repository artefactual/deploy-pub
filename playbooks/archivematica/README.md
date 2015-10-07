# Archivematica playbook

The provided playbook installs Archivematica on a local vagrant virtual machine.

## Requirements

- Vagrant 1.7 or newer
- Ansible 1.9 or newer

## How to use

1. Download the Ansible roles:
  ```
  $ ansible-galaxy install -f -r requirements.yml
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
    * Using vagrant command:
      ```
      $ vagrant provision
      ```
    * Or with ansible directly. This allows you to pass ansible-specific parameters,
      such as tags and the verbose flag. Also, don't forget to use extra-vars
      to pass the variables that are being passed in the Vagrantfile (in particular
      archivematica_src_dir )
      ```
      $ ansible-playbook -i .vagrant/provisioners/ansible/inventory/vagrant_ansible_inventory singlenode.yml \
         -u vagrant \
         --private-key .vagrant/machines/am-local/virtualbox/private_key \
         --extra-vars="archivematica_src_dir=/vagrant/src archivematica_src_environment_type=development" \
         --tags="amsrc-pipeline-instcode" \
         -v
      ```


For more archivematica development information, see: https://wiki.archivematica.org/Getting_started
