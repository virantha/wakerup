#FROM python:3-alpine
FROM alpine:latest

RUN apk update &&  \
    apk add --no-cache bash openssh-client tzdata ansible sshpass pwgen && \
    rm -rf /tmp/* && \
    rm -rf /var/cache/apk/*

WORKDIR /usr/src/app
COPY wakerup/wakerup.py \
     wakerup/plex_sleep.py \
     requirements.txt \
     run.sh \ 
     ansible/playbook.yml \
     ansible/ansible.cfg \
     ./

# This hack is widely applied to avoid python printing issues in docker containers.
# See: https://github.com/Docker-Hub-frolvlad/docker-alpine-python3/pull/13
ENV PYTHONUNBUFFERED=1
RUN python3 -m pip install --upgrade pip
RUN pip3 install -r requirements.txt
CMD ["./run.sh"]