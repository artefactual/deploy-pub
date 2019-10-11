# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  config.vm.box = ENV.fetch("VAGRANT_BOX", "ubuntu/bionic64")

  {
    "am-local" => {
      "ip" => "192.168.168.198",
      "memory" => "4096",
      "cpus" => "2",
    },
  }.each do |short_name, properties|

    # Define guest
    config.vm.define short_name do |host|
      host.vm.network "private_network", ip: properties.fetch("ip")
      host.vm.hostname = "#{short_name}.myapp.dev"
    end

    # Set the amount of RAM and virtual CPUs for the virtual machine
    config.vm.provider :virtualbox do |vb|
      vb.customize ["modifyvm", :id, "--memory", properties.fetch("memory")]
      vb.customize ["modifyvm", :id, "--cpus", properties.fetch("cpus")]
    end

  end

  # Make the project root available to the guest VM
  config.vm.synced_folder '.', '/vagrant', mount_options: ["uid=333", "gid=333"]

  # Ansible provisioning
  config.vm.provision "shell", inline: "sudo apt-get update -y &&  apt-get install -y python"

  config.vm.provision :ansible do |ansible|
    ansible.playbook = "./singlenode.yml"
    ansible.host_key_checking = false
    ansible.extra_vars = {
      "archivematica_src_dir" => "/vagrant/src/",
      "archivematica_src_environment_type" => "development",
    }
    # Accept multiple arguments, separated by colons
    ansible.raw_arguments = ENV['ANSIBLE_ARGS'].to_s.split(':')
  end
end
