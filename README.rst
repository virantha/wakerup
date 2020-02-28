WakerUp - Automatically wake and sleep a Plex Server
====================================================

.. |reg|    unicode:: U+000AE .. REGISTERED SIGN

WakerUp, usable as a Docker container, is designed to automatically bring a
standalone Linux (Ubuntu) server running Plex in and out of sleep. It
consists of two main scripts that are run in parallel, and also requires a
router that can log firewall rules:

1. **wakerup.py** Monitors a log file, and sends a WOL packet when a specified pattern is seen.  Typically, you
   would use this to monitor your firewall logs for activity on port 32400 (the Plex server port), which usually happens
   when your plex browser or phone app tries to log in to the Plex login servers.
2. **plex_sleep.py**  Monitors a Plex server over its web API for client connections and transcoding sessions.  Once inactivity
   is detected, it will put the server to sleep via a pm-suspend command run over ssh.

* Free and open-source software: ASL2 license
* Source: https://github.com/virantha/wakerup


Docker Installation
-------------------
On Unraid, do the following:

- Add https://github.com/virantha/docker-containers to your Unraid template repository
    .. image:: images/img_unraid_template.png
        :width: 600px
- Add a new `wakerup` container with the following settings:
    .. image:: images/img_unraid_settings.png
        :width: 600px

- Setup:
    - You will need to give your UNIX login password to your Plex server in
      the PLEX_PASSWORD field. This is needed for the first time setup for copying
      ssh keys and adding pm-suspend to the sudoers list. After the first run of
      the docker, you can go ahead and delete your password from this field (just
      leave it blank and save). Your ssh password will continue to be stored in an
      encrypted file in your docker config directory (%appdata%) to make sure these
      ssh and sudoers settings stay intact.

    - Your firewall/router will need to syslog to a file that this docker has
      access to. The easiest way is to set your router to remote syslog to
      Unraid (enable this in Unraid Settings -> Syslog server), and then pass the log
      directory in Unraid to this docker via the Container path */logs*.  Then, you need
      to enter the text in the *Router regex* field that the script will search for in the log (usually just a 
      destination port of 32400) for triggering the wakeup.  You can also enter a full regular expression in this field.

    - You must use the *host* networking docker option, otherwise this container
      will not be able to send ICMP (pings) to your Plex server.


    
How it works:
-------------

wakerup.py
##########

The wakeup script continually monitors the specified logfile using the python *watchdog* package.
The typical way you would set this logfile up is to setup your router to remotely syslog any
port 32400 activity to its firewall logfile.  Recent versions of Unraid have a syslog server
built-in, so just enable that and have your router log to a directory on your cache drive.  This 
script does not depend on any external tools, and uses a pure python library called wakeonlan to 
send the magic packet.

For the firewall settings, please look at your relevant manual.  As an example, I run
and EdgeOS device (EdgeRouter), and have the following config settings:

.. code-block:: yaml

    firewall {
        ...
        name LAN_LOCAL {
            default-action accept
            description ""
            rule 1 {
                action accept
                description "plex detect"
                destination {
                    group {
                    }
                    port 32400
                }
                log enable
                protocol tcp_udp
            }
        }
    }
    ...
    service {
        nat {                                                                      
            rule 1 {                                                               
                description plex                                                   
                destination {                                                      
                    group {                                                        
                        address-group ADDRv4_eth1                                  
                    }                                                              
                    port 32400                                                     
                }                                                                  
                inbound-interface eth1                                             
                inside-address {                                                   
                    address YOUR_PLEX_IP
                    port 32400                                                     
                }                                                                  
                log enable                                                         
                protocol tcp_udp                                                   
                type destination                                                   
            }                 
        }
    }
    syslog {                                                                   
    ...
        host YOUR_UNRAID_IP {                                                    
            facility all {                                                     
                level notice                                                   
            }                                                                  
        }                                                                      
    }  

Although you don't need to deal with the configuration file for this script with the docker,
here is what needs to be in it for wakerup.py to work:

.. code-block:: yaml

    plex:
        # Minimum time (seconds) betweek successive WOL packets (so we don't spam the network with broadcasts)
        min_interval: 10

        # MAC address needed for Wake-On-Lan magic packet
        mac_addr: "00:23:24:99:E1:0F"
        
        # IP address needed for pinging to see if server is up or not
        ip: "192.168.9.183"

        # The log file location that we're monitoring for activity that signals we should wake a server 
        log_filename: "/logs/syslog-192.168.9.1.log"

        # The string we're looking for in the log file (in this example, it's an EdgeOS log file with destination port 32400) that signals activity
        regex: "DPT=32400"


plex_sleep.py
#############
This script continually monitors a linux Plex server via its web api for activity, and then suspends it by running `pm-suspend` via ssh.
A typical configuration file for this script (which the docker sets up for you automatically) is given below:

.. code-block:: yaml

    user: 'plex'
    server: '192.168.9.183'
    port: 32400

    # Amount of time in seconds that server is idle for before sleeping (600 = 10 minutes)
    timeout: 600

    # Plex auth token
    token: XXXXX

    # Plex library scan interval
    scan_interval: "movie:43200,tv:43200,photo:172800,artist:172800

The main piece of information obviously is the Plex server IP address and port (use the default 32400).  You will also need
the Plex authentication token which can be found as described `here <https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/>`_ 
for the script to be able to connect to the web api that Plex provides.  In addition, we need the UNIX username in order to ssh into the
machine.  

The *scan_interval* is a comma separated list of each library type's scan interval in seconds.  The main types that Plex uses are:

- **movie** for Movies
- **show** for TV Shows
- **artist** for Music
- **photo** for Photos

Once configured, the script runs the following tasks:

- Connects to the plex server (waits for it to awaken if necessary)
- Starts monitoring the following activities:
    - Active clients (iOS apps that are browsing the server, for example)
    - Active streaming sessions
    - Active transcodes including background sync transcodes
    - Library scans
- It also checks the timestamps of the libraries against the config file's scan intervals, and triggers
  a library scan for any that exceed the scan interval.
- If there are no monitored activities running, then it puts the server to sleep via ssh with the pm-suspend command. 
  The script relies on public key authentication to ensure there is no password prompt with the ssh command (this is 
  automatically set up through the docker startup), and the presence of ``pm-utils`` on this server.  The suspend command
  is actually scheduled for the next minute via the UNIX ``at`` command to allow the ssh command to exit cleanly before sleep.
- The script then waits for the server to go to sleep (monitored via ping ICMP packets), and then it waits for the
  server to start responding to pings again before starting this loop all over again.


Credits
#######

* Virantha N. Ekanayake :gh_user:`virantha` - lead developer

Disclaimer
##########

The software is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  Licensed under ASL 2.0

