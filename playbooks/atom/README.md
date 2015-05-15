# AtoM Playbook

## How to use
1. Install roles used by the playbook
  ```
  $ ansible-galaxy install -r requirements.yml
  ```  
2. Create the test VM using vagrant  
  ```
  $ vagrant up
  ```
3. Run playbook to install AtoM on the vagrant VM  
  ```
  ansible-playbook -i hosts atom.yml --extra-vars "atom_flush_data=true atom_worker_setup=true"
  ```

## Known issues

 * If the playbook stops with an error when connecting to the MySQL server, log in to the VM and restart percona:  
  `# service mysql restart`
* If getting a 502 error instead of the AtoM page, log in to the VM and try restarting php5-fpm:  
  `# service php5-fpm restart`

## Notes
vagrant configuration uses the guidelines [here](http://hakunin.com/six-ansible-practices#build-a-convenient-local-playground).
