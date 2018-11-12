# Archivematica playbook

The provided playbook installs Archivematica on a local vagrant virtual
machine using rpm packages. For instructions on using deploy-pub to install
Archivematica on a Digital Ocean droplet, see the [Digital Ocean Droplet
Deploy](docs/digital-ocean-install-example.rst) document.

## Requirements

- Vagrant 1.9.2 or newer (note that vagrant 1.9.1 has a bug when restarting network services in RHEL https://github.com/mitchellh/vagrant/pull/8148). Vagrant has changed its image repository URLs, so when using an old Vagrant version, see https://github.com/hashicorp/vagrant/issues/9442
- Ansible 2.2 or newer

## How to use

1. Create the virtual machine and provision it:
  ```
  $ vagrant up
  ```
  After provisioning ends, Achivematica UI should be accessible at http://xxx.xxx.xxx.xxx:81 and the Storage Service UI at http://xxx.xxx.xxx.xxx:8001 where xxx.xxx.xxx.xxx is the IP address specified in the `ip` variable of the Vagrantfile

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

5. If you get errors regarding the Vagrant shared folders, they are usually due
to different versions of VirtualBox. One way to fix it is using a Vagrant
plugin that installs the host's VirtualBox Guest Additions on the guest system:
  ```
  $ vagrant plugin install vagrant-vbguest
  $ vagrant vbguest
  ```

For more archivematica development information, see: https://wiki.archivematica.org/Getting_started
