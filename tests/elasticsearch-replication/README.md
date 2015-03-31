Steps:

Create the virtual machines:

```bash
vagrant up --no-provision --parallel
```

Provision the NFS server:

```bash
vagrant provision nfs
```

Install ES in all the nodes of the cluster and configure the repository:

```bash
ansible-playbook -i hosts --limit es_servers --tags elasticsearch,elasticsearch-repository
```

Populate index in the cluster:

```bash
$ ./populate-index.sh
```

Take a snapshot and test restoring it:

```bash
$ ansible-playbook -i hosts --limit es_servers --tags elasticsearch-snapshot,elasticsearch-restore
```
