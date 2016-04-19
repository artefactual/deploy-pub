# Archivematica playbook

The provided playbook installs Archivematica on a cluster of virtual machines provisioned by Vagrant.

You should not use this environment in production but you may want to roll your own based on it.

## Requirements

- Vagrant 1.8 or newer
- Ansible 2.0 or newer

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
    * Using vagrant and custom ANSIBLE_ARGS, e.g. install Storage Service only:
        ```
        $ ANSIBLE_ARGS="--tags=amsrc-ss" vagrant provision
        ```

For more archivematica development information, see: https://wiki.archivematica.org/Getting_started
