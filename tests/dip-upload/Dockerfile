ARG UBUNTU_VERSION=22.04

FROM ubuntu:${UBUNTU_VERSION}

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && apt-get install -y sudo openssh-server rsync locales && apt-get clean

RUN useradd --home-dir /home/ubuntu --system ubuntu

COPY --chown=ubuntu:ubuntu --chmod=600 ssh_pub_key /home/ubuntu/.ssh/authorized_keys

RUN mkdir -p /etc/sudoers.d/ && echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers.d/ubuntu

EXPOSE 22
EXPOSE 80
EXPOSE 8000

CMD [ "/sbin/init" ]
