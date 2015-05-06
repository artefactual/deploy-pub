run:

install ansible:
pip install ansible

install vagrant

read http://hakunin.com/six-ansible-practices

ansible-galaxy install -r requirements.yml
ansible-playbook -i hosts singlenode.yml --private-key=~/.vagrant.d/insecure_private_key
