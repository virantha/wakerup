#!/bin/sh
echo 
echo "========================================"
echo "Starting docker..."
echo "========================================"
# Generate ssh keys if not present
if [ -f /config/ssh/id_rsa.pub ]; then
    echo "SSH keys exist, yay!"
else
    echo "SSH keys do not exist (first run?)"
    echo "Creating new keys.."
    mkdir /config/ssh
    ssh-keygen -t rsa -f /config/ssh/id_rsa -q -N ""
    echo "New ssh keys generated!"
fi

if [ ! -d ~/.ssh ]; then                                                                           
    mkdir -p ~/.ssh                                                                                   
fi
if [ ! -f ~/.ssh/id_rsa.pub ]; then
    ln -s -f /config/ssh/id_rsa.pub ~/.ssh/id_rsa.pub                                                 
    ln -s -f /config/ssh/id_rsa ~/.ssh/id_rsa                                                         
fi          

echo -n "Writing config for wakerup script /config/config_wakerup.yml ... "
cat <<EOF > /config/config_wakerup.yml
plex:
    min_interval: 10   # interval between sending successive wol packets (seconds)
    mac_addr: "$PLEX_MAC_ADDR"
    ip: "$PLEX_SERVER"
    log_filename: "$PLEX_LOG_FILENAME"
    regex: "$PLEX_REGEX"
EOF
echo "done"

echo -n "Writing config for sleep script /config/config_plex_sleep.yml ... "
cat <<EOF > /config/config_plex_sleep.yml
user: "$PLEX_USER"
server: "$PLEX_SERVER"
port: 32400
timeout: $PLEX_IDLE_TIMEOUT
token: "$PLEX_TOKEN"
scan_interval: $PLEX_SCAN_INTERVAL
EOF
echo "done"

# Create the hosts inventory
echo "Making sure the plex server is properly configured by using ansible"
echo
echo -n "hosts.yml ... "
cat <<EOF > hosts.yml
all:
   hosts:
      $PLEX_SERVER:
         ansible_user: $PLEX_USER
         ansible_ssh_extra_args: '-o StrictHostKeyChecking=no'
EOF
echo "created"

# Create the vault password file as long as we have a password in the environment
if [ ! -z "$PLEX_PASSWORD" ]; then

    echo "Plex server password is present, so rebuilding ansible password vault"
    echo -n "Creating ansible vault password /config/vault_pass.txt ... "
    pwgen -s -1 > /config/vault_pass.txt
    chmod 400 /config/vault_pass.txt
    echo "done"

    # Create the ssh password file
    echo -n "Creating ansible plaintext password file /config/passwords.yml ... "
    cat <<EOF > /config/passwords.yml
    ansible_ssh_pass: "$PLEX_PASSWORD"
    ansible_sudo_pass: "$PLEX_PASSWORD"
EOF
    echo "done"
    # Encrypt this file with the vault password
    echo -n "Encrypting ansible password file /config/passwords.yml ... "
    ansible-vault encrypt --vault-password-file /config/vault_pass.txt /config/passwords.yml
    echo "done"
else
    echo "Plex server password has not been supplied (PLEX_PASSWORD)"
fi

if [ -f /config/vault_pass.txt ] && [ -f /config/passwords.yml ]; then
    ansible-playbook -i hosts.yml --vault-password-file /config/vault_pass.txt playbook.yml
else
    echo "WARNING: No password files detected for ansible to configure Plex server ssh keys and suspend commands"
    echo "WARNING: Please make sure to supply PLEX_PASSWORD in the docker configuration in at least one docker start to make sure everything is configured properly."
fi

echo "Configuration is complete... Starting processes..."
if [ $PLEX_DEBUG == "1" ]; then
    echo "DEBUG detected"
    DEBUG_FLAG='-d'
else
    DEBUG_FLAG=''
fi

# Start the first process
python3 wakerup.py -v $DEBUG_FLAG /config/config_wakerup.yml &
PROCESS_1=$!
status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start wakerup: $status"
  exit $status
fi

# Start the second process
python3 plex_sleep.py -v $DEBUG_FLAG /config/config_plex_sleep.yml &
PROCESS_2=$!
status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start plex_sleep: $status"
  exit $status
fi

# Naive check runs checks once a minute to see if either of the processes exited.
# This illustrates part of the heavy lifting you need to do if you want to run
# more than one service in a container. The container exits with an error
# if it detects that either of the processes has exited.
# Otherwise it loops forever, waking up every 60 seconds
echo
echo "========================================"
echo "WakerUp is running..."
echo "========================================"

function cleanup()
{
    echo "terminating..."
    kill -SIGTERM $PROCESS_2
    kill -SIGTERM $PROCESS_1
    exit 0
}

trap cleanup SIGTERM 

while sleep 1; do
  ps aux |grep wakerup |grep -q -v grep
  PROCESS_1_STATUS=$?
  ps aux |grep plex_sleep |grep -q -v grep
  PROCESS_2_STATUS=$?
  # If the greps above find anything, they exit with 0 status
  # If they are not both 0, then something is wrong
  if [ $PROCESS_1_STATUS -ne 0 -o $PROCESS_2_STATUS -ne 0 ]; then
    echo "One of the processes has already exited."
    exit 1
  fi
done