# Archivematica playbook

The provided playbook installs Archivematica on a remote virtual
machine. 

## Requirements

- Passwordless SSH access to the destination server
- Ansible 2.9 or newer

## How to use

1. Download the Ansible roles:
  ```
  $ ansible-galaxy install -f -p roles/ -r requirements.yml
  ```

2. Create the inventory file:
  ```
  $ echo 'am-centos8       ansible_host=<host ip>       ansible_user=<user>' > hosts
  ```
  
3. Verify ssh access to the VM, run:
  ```
  $ ssh <user>@<host> "sudo whoami"
  root  
  ```

4. Install with
  ```
  $ ansible-playbook -i hosts singlenode.yml
  ```

5. The ansible playbook `singlenode.yml` specified in the Vagrantfile will provision using the branches of archivematica specfied in the file `vars-singlenode.yml`. Edit this file if need to deploy other branches.  



# Login and credentials

If you are using the default values in vars-singlenode-XXXX.yml and Vagrantfile files, the login URLS are:

* Dashboard:       http://\<host ip\>
* Storage Service: http://\<host ip\>:8000

Credentials:

* user: admin
* password: archivematica

For more archivematica development information, see: https://wiki.archivematica.org/Getting_started
