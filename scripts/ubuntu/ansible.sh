#!/bin/bash -eux

apt-get install -y software-properties-common python-software-properties
apt-add-repository ppa:ansible/ansible
apt-get update
apt-get install -y ansible
