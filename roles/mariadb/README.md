# MariaDB role

Installs a MariaDB server from the repositories of the MariaDB Foundation,
sets the root password, and creates databases and users.

## Supported platforms

- Ubuntu 22.04 and 24.04
- Rocky Linux 8 and 9

The role requires the `community.mysql` collection on the controller, which
the `ansible` package includes, and installs the PyMySQL connector that its
modules need on the managed host.

## Role variables

Check `defaults/main.yml` for the complete list and their default values.

```yaml
mariadb_version: "11.8"
```

The release series to install. The repositories carry the latest release of
the series.

```yaml
mariadb_root_password: ""
```

The password of the `root@localhost` account. The account keeps the
passwordless `unix_socket` authentication of a new installation, so the local
root user can still connect without the password, which the maintenance
scripts of the packages rely on. When the variable is empty, the account only
accepts `unix_socket` authentication. The role writes `/root/.my.cnf` with the
credentials so that the MySQL modules of Ansible and the command line clients
run by root connect without further configuration.

```yaml
mariadb_databases: []
mariadb_users: []
```

The databases and users to create. The entries take the same keys as the
`mysql_databases` and `mysql_users` variables of the `artefactual.percona`
role, so a variables file can define them once and pass them to either role:

```yaml
mariadb_databases: "{{ mysql_databases }}"
mariadb_users: "{{ mysql_users }}"
```

The server settings in `defaults/main.yml`, such as `mariadb_bind_address`
and `mariadb_max_allowed_packet`, are written to a configuration file that
the server reads after the files shipped by the packages.

The `mariadb-client-compat` and `MariaDB-client-compat` packages are
installed so that the `mysql` command names keep working.

## Example playbook

```yaml
- hosts: "all"
  roles:
    - role: "mariadb"
      become: "yes"
      vars:
        mariadb_root_password: "secret"
        mariadb_databases:
          - name: "MCP"
            encoding: "utf8mb4"
            collation: "utf8mb4_0900_ai_ci"
        mariadb_users:
          - name: "archivematica"
            pass: "demo"
            priv: "MCP.*:ALL,GRANT"
            host: "localhost"
```

The `utf8mb4_0900_ai_ci` collation that the Archivematica roles use by
default is available from MariaDB 11.4.5.

## Containers

The role writes the server configuration before it installs the packages, so
a new installation starts with its final settings and is never restarted. The
rootless Podman containers of the test suites cannot restart services, and
this is what lets the role provision them. Changing the configuration of an
existing installation restarts the server.

The packaged service requests the `CAP_IPC_LOCK` ambient capability, which
rootless Podman cannot grant, and the systemd of Rocky Linux 8 refuses to
start the server without it. Set `mariadb_ambient_capabilities` to an empty
value in containers; the role writes it to a drop-in of the service.

## License

AGPLv3
