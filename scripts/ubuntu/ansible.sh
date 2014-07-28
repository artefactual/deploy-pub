#!/bin/bash -eux

apt-get install -y python-software-properties
apt-add-repository ppa:rquillo/ansible
apt-get update
apt-get install -y ansible
