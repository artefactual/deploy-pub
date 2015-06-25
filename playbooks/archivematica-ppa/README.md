# archivematica-ppa playbook

The provided playbook installs archivematica on a local vagrant VM, from launchpad ppa:archivematica packages

## How to use
1. Install roles used by the playbook
  ```
  $ ansible-galaxy install -r requirements.yml
  ```  
2. Create the test VM using vagrant  
  ```
  $ vagrant up
  ```
3. Run playbook to install Archivematica on the vagrant VM  
  ```
  $ ansible-playbook -i hosts singlenode.yml
  ```
4. To ssh to the VM, use the provided ssh.config file. Example:
  ```
  $ ssh -F ssh.config 192.168.168.194
  ```

  
## Notes
vagrant configuration uses the guidelines [here](http://hakunin.com/six-ansible-practices#build-a-convenient-local-playground).
