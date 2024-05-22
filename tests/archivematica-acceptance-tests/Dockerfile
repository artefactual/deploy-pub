ARG TARGET=server
ARG DOCKER_IMAGE_NAME=ubuntu
ARG DOCKER_IMAGE_TAG=22.04

FROM ubuntu:20.04 AS install_ubuntu_20.04

ENV DEBIAN_FRONTEND noninteractive

RUN set -ex \
	&& apt-get update \
	&& apt-get install -y \
        locales \
        openssh-server \
        rsync \
        sudo \
    && apt-get clean

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

FROM ubuntu:22.04 AS install_ubuntu_22.04

ENV DEBIAN_FRONTEND noninteractive

RUN set -ex \
	&& apt-get update \
	&& apt-get install -y \
        locales \
        openssh-server \
        rsync \
        sudo \
    && apt-get clean

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

FROM rockylinux:8 AS install_rockylinux_8

RUN set -ex \
    && dnf -y update \
    && dnf -y install coreutils --allowerasing \
    && dnf -y install \
        glibc-langpack-en \
        openssh-server \
        sudo \
    && dnf clean all

FROM rockylinux:9 AS install_rockylinux_9

RUN set -ex \
    && dnf -y update \
    && dnf -y install coreutils --allowerasing \
    && dnf -y install \
        glibc-langpack-en \
        openssh-server \
        python-unversioned-command \
        sudo \
    && dnf clean all

FROM almalinux:9 AS install_almalinux_9

RUN set -ex \
    && dnf -y update \
    && dnf -y install coreutils --allowerasing \
    && dnf -y install \
        glibc-langpack-en \
        openssh-server \
        python-unversioned-command \
        sudo \
    && dnf clean all

FROM oraclelinux:9 AS install_oraclelinux_9

    RUN set -ex \
        && dnf -y update \
        && dnf -y install coreutils --allowerasing \
        && dnf -y install \
            glibc-langpack-en \
            openssh-server \
            python-unversioned-command \
            sudo \
        && dnf clean all

FROM install_${DOCKER_IMAGE_NAME}_${DOCKER_IMAGE_TAG} as server

RUN useradd --home-dir /home/ubuntu --system ubuntu

COPY --chown=ubuntu:ubuntu --chmod=600 ssh_pub_key /home/ubuntu/.ssh/authorized_keys

RUN mkdir -p /etc/sudoers.d/ && echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers.d/ubuntu

EXPOSE 22
EXPOSE 80
EXPOSE 8000

CMD [ "/sbin/init" ]

FROM ${TARGET}
