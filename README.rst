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
    .. image:: img_unraid_template.png
        :width: 600px
- Add a new `wakerup` container with the following settings:
    .. image:: img_unraid_settings.png
        :width: 600px

- Things to note:
    - You will need to give your UNIX login password to your Plex server in the PLEX_PASSWORD field.  This is needed for the first time setup for copying ssh keys and adding pm-suspend to 
      the sudoers list.  After the first run of the docker, you can go ahead and delete your password from this field (just leave it blank and save).  Your ssh password will continue to
      be stored in an encrypted file in your docker config directory (%appdata%) to make sure these ssh and sudoers settings stay intact. 
    - You must use the *host* networking option, otherwise this container will not be able to send ICMP (pings) to your Plex server.

    
How it works:
-------------

wakerup.py
##########
The wakeup script continually monitors the specified logfile using the python *watchdog* package.
The typical way you would set this logfile up is to setup your router to remotely syslog any
port 32400 activity to its firewall logfile.  Recent versions of Unraid have a syslog server
built-in, so just enable that and have your router log to a directory on your cache drive.

For the firewall settings, please look at your relevant manual.  As an example, I run
and EdgeOS device (EdgeRouter), and have the following config settings:

.. code-block:: yaml

    firewall {
        ...
        name LAN {
            default-action accept
            description ""
            rule 1 {
                action accept
                description "plex detect"
                destination {
                    group {
                        address-group ADDRv4_eth1
                    }
                    port 32400
                }
                log enable
                protocol tcp_udp
            }
            rule 2 {
                action accept
                description "plex detect 2"
                destination {
                    address YOUR_PLEX_IP
                }
                disable
                log enable
                protocol tcp_udp
            }
        }
    service {
    ...
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

plex_sleep.py
#############


Credits
#######

* Virantha N. Ekanayake :gh_user:`virantha` - lead developer

Disclaimer
##########

The software is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  Licensed under ASL 2.0

