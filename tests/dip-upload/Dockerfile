ARG BASE_IMAGE=docker.io/jrei/systemd-ubuntu
ARG BASE_IMAGE_TAG=24.04

FROM ${BASE_IMAGE}:${BASE_IMAGE_TAG} AS server

ENV container=podman
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# Install systemd-capable base utilities
RUN set -eux; \
    if command -v apt-get >/dev/null 2>&1; then \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            systemd systemd-sysv dbus \
            sudo openssh-server rsync curl locales procps \
            iproute2 iputils-ping python3; \
        locale-gen en_US.UTF-8; \
    elif command -v dnf >/dev/null 2>&1; then \
        dnf -y update; \
        dnf -y swap coreutils-single coreutils;   \
        dnf -y swap curl-minimal curl; \
        dnf -y install \
            systemd openssh-server sudo rsync procps-ng \
            iproute iputils glibc-langpack-en python3; \
        dnf clean all; \
    elif command -v microdnf >/dev/null 2>&1; then \
        microdnf -y update; \
        microdnf -y swap coreutils-single coreutils; \
        microdnf -y swap curl-minimal curl; \
        microdnf -y install \
            systemd openssh-server sudo rsync curl procps-ng \
            iproute iputils glibc-langpack-en python3; \
        microdnf clean all; \
    else \
        echo "Unsupported base image for systemd container" >&2; \
        exit 1; \
    fi

# Ensure expected user exists with passwordless sudo
RUN set -eux; \
    groupadd -f artefactual || true; \
    if ! getent passwd artefactual >/dev/null 2>&1; then \
      useradd -m -s /bin/bash -g artefactual artefactual; \
    fi; \
    usermod -U artefactual || true; \
    mkdir -p /home/artefactual/.ssh /etc/sudoers.d; \
    chmod 700 /home/artefactual/.ssh; \
    chown -R artefactual:artefactual /home/artefactual; \
    echo 'artefactual:artefactual' | chpasswd || true; \
    echo 'artefactual ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/artefactual; \
    chmod 0440 /etc/sudoers.d/artefactual

COPY --chown=artefactual:artefactual --chmod=600 ssh_pub_key /home/artefactual/.ssh/authorized_keys

# Make sure SSHD is enabled when systemd boots
RUN set -eux; \
    mkdir -p /var/run/sshd; \
    if [ -f /lib/systemd/system/ssh.service ]; then \
        ln -sf /lib/systemd/system/ssh.service /etc/systemd/system/multi-user.target.wants/ssh.service; \
    elif [ -f /usr/lib/systemd/system/sshd.service ]; then \
        ln -sf /usr/lib/systemd/system/sshd.service /etc/systemd/system/multi-user.target.wants/sshd.service; \
    fi

COPY container-entrypoint.sh /usr/local/sbin/container-entrypoint.sh
RUN chmod 755 /usr/local/sbin/container-entrypoint.sh

STOPSIGNAL SIGRTMIN+3
VOLUME [ "/sys/fs/cgroup" ]

EXPOSE 22
EXPOSE 80
EXPOSE 8000

CMD [ "/usr/local/sbin/container-entrypoint.sh" ]
