FROM python:3-alpine

RUN apk update &&  \
    apk add --no-cache bash openssh-client tzdata ansible sshpass pwgen && \
    rm -rf /tmp/* && \
    rm -rf /var/cache/apk/*

WORKDIR /usr/src/app
COPY wakerup/wakerup.py \
     wakerup/plex_sleep.py \
     requirements.txt \
     run.sh \ 
     wakerup/config_wakerup.sample.yml \
     wakerup/config_plex_sleep.sample.yml \
     ansible/playbook.yml \
     ./

# This hack is widely applied to avoid python printing issues in docker containers.
# See: https://github.com/Docker-Hub-frolvlad/docker-alpine-python3/pull/13
ENV PYTHONUNBUFFERED=1
RUN python -m pip install --upgrade pip
RUN pip3 install -r requirements.txt
#WORKDIR /usr/src/app/wakerup
#CMD ["python", "wakerup.py", "config.yml"]
CMD ./run.sh