Role Name
========

This role installs and setup NFS server.

Requirements
------------

Ansible 1.4 or higher.

Role Variables
--------------

```yaml
nfs_exported_directories: []
nfs_ports:
  - {name: LOCKD_TCPPORT,       value: 32803}
  - {name: LOCKD_UDPPORT,       value: 32769}
  - {name: MOUNTD_PORT,         value: 892}
  - {name: RQUOTAD_PORT,        value: 875}
  - {name: STATD_PORT,          value: 662}
  - {name: STATD_OUTGOING_PORT, value: 2020}
```

Dependencies
------------

None.

Example Playbook
-------------------------

```yaml

- role: nfs
  nfs_exported_directories:
      - path: /export/test1
        hosts:
          - {name: 192.168.0.0/16, options: ["ro", "sync"]}
          - {name: 10.0.0.5, options: ["rw", "sync", "no_root_squash"]}
      - path: /export/test2
        hosts:
          - {name: "*", options: []}
```

License
-------

BSD

Author Information
------------------

This role was created in 2014 by Atsushi Sasaki (@atsaki).
