ARG UBUNTU_VERSION=22.04

FROM ubuntu:${UBUNTU_VERSION}

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && apt-get install -y sudo openssh-server rsync locales && apt-get clean


CMD [ "/sbin/init" ]
