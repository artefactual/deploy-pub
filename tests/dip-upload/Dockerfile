ARG UBUNTU_VERSION=22.04

FROM ubuntu:${UBUNTU_VERSION}

ENV DEBIAN_FRONTEND noninteractive

# Ubuntu 24.04 and later Docker images include a default user with UID (1000)
# and GID (1000). Remove this user to prevent conflicts with the USER_ID and
# GROUP_ID build arguments.
RUN set -ex \
  && id -u ubuntu >/dev/null 2>&1 \
  && userdel --remove ubuntu || true

RUN apt-get update && apt-get install -y sudo openssh-server rsync locales && apt-get clean

RUN useradd --home-dir /home/ubuntu --system ubuntu

COPY --chown=ubuntu:ubuntu --chmod=600 ssh_pub_key /home/ubuntu/.ssh/authorized_keys

RUN mkdir -p /etc/sudoers.d/ && echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers.d/ubuntu

EXPOSE 22
EXPOSE 80
EXPOSE 8000

CMD [ "/sbin/init" ]
