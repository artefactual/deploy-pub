# Packer templates

## How to build them

* Change directory

```bash
cd vagrant-base-ubuntu-14.04-amd64
```

* Run packer

```bash
PACKER_CACHE_DIR="$HOME/.packer_cache" packer build template.json
```

## Vagrant boxes

Boxes like ```vagrant-box-atom``` start being built from a OVF file that must
be generated previously building the ```vagrant-base-ubuntu-14.04-amd64```
template.

Vagrant boxes:

* vagrant-box-atom: AtoM box for developers and demos
