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
