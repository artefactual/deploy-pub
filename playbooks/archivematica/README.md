# Archivematica playbook

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
  
## Notes
vagrant configuration uses the guidelines [here](http://hakunin.com/six-ansible-practices#build-a-convenient-local-playground).
