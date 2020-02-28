"""plex_sleep.py

    Usage:
        plex_sleep [-vdh] CONFIGFILE

    Keeps track of client sessions and transcodes, and suspends the current
    server if there's no activity for a predetermined amount of time.

    Requires a configuration in a file called 'config_plex_sleep.yml', with an entry
    labelled 'token' that is set to the Plex authentication token for your server
    
    Arguments:
        CONFIGFILE      configuration file

    Options:
        -h --help       Help message
        -v              Verbose
        -d              Debug
        --version       Version info
    
"""
__version__ = "0.1.0"

import time, sys, os, logging, signal
from plexapi.server import PlexServer
from pythonping import ping
import requests
import json
import yaml
import docopt

log = logging.getLogger(__name__)

class PlexSleep:
    """ Use the plexapi to monitor:
            - client connections
            - streaming sessions
            - transcoding sessions (for things like sync)

    """
    config_filename = 'config_plex_sleep.yml'
    def __init__(self, config_filename):

        log.info(f'plex_sleep v{__version__}')
        self.load_config(config_filename)
        self.activity = time.time()
        self.baseurl = f'http://{self.server}:{self.port}'

        self.wait_for_resume()
        log.info(f"Connnecting to plex server at {self.baseurl}...")
        self.plex = PlexServer(self.baseurl, self.token)
        log.info(f"Connnected")

        self.pending_refreshes = {}
        self.watch_server()

    def load_config(self, filename):
        with open(filename) as f:
            self.config = yaml.load(f, Loader=yaml.FullLoader)

        self.user = self.config.get('user')
        self.server = self.config.get('server', 'localhost')
        self.port = self.config.get('port', '32400')
        self.timeout = self.config.get('timeout', 10*60)   # Default to 10 minutes before sleeping
        self.check_interval = self.config.get('check_interval', 60)  # Check every minute to update who's connected

        # Default scan intervals
        self.library_scan_interval = {'movie': 60*60*12,     # 12 hours,
                                      'show':  60*60*12,     # TV shows = 12 hours
                                      'artist': 60*60*48,    # Music = 2 days
                                      'photo': 60*60*24,     # Photos = 1 day,
                                      }
        scan_intervals = self.config.get('scan_interval', "movie:43200")
        for entry in scan_intervals.split(','):
            lib_type, lib_interval = entry.split(':')
            lib_type = lib_type.strip()
            lib_interval = lib_interval.strip()
            self.library_scan_interval[lib_type] = int(lib_interval)
            # Catch some common errors that a user might make
            if lib_type == 'music' or lib_type == 'mp3':
                log.warn(f'For scan_interval, you have used {lib_type}, but please use "artist" for Music libraries')
            if lib_type == 'tv' or lib_type == 'tv shows':
                log.warn(f'For scan_interval, you have used {lib_type}, but please use "show" for TV libraries')
        
        for lib_type, lib_interval in self.library_scan_interval.items():
            log.info(f'Scan interval for {lib_type} libraries: {self.library_scan_interval[lib_type]} seconds')

        # Get the token from the environment first, then look for it in the config file
        if 'PLEX_TOKEN' in os.environ:
            self.token = os.environ.get('PLEX_TOKEN')
        elif 'token' in self.config:
            self.token = self.config.get('token')
        else:
            log.error(f'No PLEX_TOKEN environment variable set or "token" statement in config file (used to connect to Plex server')
            log.error('Exiting')
            sys.exit(-1)

    def watch_server(self):
        idle_time = 0
        last_client_time = time.time()
        log.info('Started monitoring')
        while True:
            n_clients = self.get_num_clients()
            n_sess = self.get_num_sessions()
            n_trans = self.get_num_transcode_sessions()
            n_activity = self.get_activity_report()
            n = n_clients + n_sess + n_trans + n_activity
            self.refresh_libraries()

            if n>0: # People are browsing the server
                last_client_time = time.time()
                log.debug(f'Active clients:{n_clients}|sessions:{n_sess}|transcodes:{n_trans}|scans:{n_activity}')
            else:
                idle_time = time.time() - last_client_time
                if idle_time > self.timeout:
                    log.info(f'Plex server idle for {int(idle_time/60)} minutes. Suspending...')
                    if self._is_alive(self.server):
                        os.system(f"""ssh -o StrictHostKeyChecking=no {self.user}@{self.server} 'echo "sudo pm-suspend" | at now + 1 minute'""")
                    self.wait_for_suspend()
                    self.wait_for_resume()
                    log.info('resuming...')
                    last_client_time = time.time()
                else:
                    log.debug(f'Plex server has been idle for {int(idle_time/60)} minutes')
            time.sleep(self.check_interval)

    def _is_alive(self, server):
        r = ping(server, count=1, timeout=1)
        return r.success()

    def wait_for_suspend(self):
        log.info(f'waiting for {self.server} to sleep')
        while True:
            if self._is_alive(self.server):
                log.debug('ping is alive')
                time.sleep(5)
            else:
                log.info(f'{self.server} is asleep')
                return

    def wait_for_resume(self):
        log.info(f'waiting for {self.server} to awaken')
        while True:
            try:
                if self._is_alive(self.server):
                    log.info(f'{self.server} is awake')
                    return
                else:
                    raise OSError
            except OSError:
                log.debug('ping is dead, waiting...')
                time.sleep(self.check_interval)
                # Probably errno 64 Host is down
                
    def _json_query(self, end_point):
        """
            Make a custom query that returns json instead of xml like Plex's default
            end_point:  '/status/sessions'
        """
        headers = self.plex._headers()
        headers['Accept'] = 'application/json'
        url = self.plex.url(end_point)
        response = requests.get(url, headers=headers)
        return response.text

    def get_num_sessions(self):
        # Any client/app watching a stream
        return self._parse_count('/status/sessions')
        
    def get_num_clients(self):
        # Any client/app browsing the server
        return self._parse_count('/clients/')

    def get_num_transcode_sessions(self):
        # Transcodes to a player or a sync
        return self._parse_count('/transcode/sessions')

    def get_activity_report(self):
        # Any library scans running on the server are reported here
        return self._parse_count('/activities')

    def _parse_count(self, end_point):
        if self._is_alive(self.server):
            j = self._json_query(end_point)
            d = json.loads(j)
            log.debug(json.dumps(d, indent=4) )
            return int(d['MediaContainer']['size'])
        else:
            return 0

    def refresh_libraries(self):
        """Trigger a rescan of any library that was last scanned earlier than
           our library_scan_interval
        """

        # Get the library api
        end_point = '/library/sections'
        j = self._json_query(end_point)
        d = json.loads(j)
        log.debug(json.dumps(d, indent=4) )
        current_time = int(time.time())

        # Clear out any pending refresh marks that are older than 10 minutes
        #   - This is for the corner case where we marked something for refresh, it started refreshing
        #     and then it finished refreshing before this function was called again.
        #for r, start_time in dict(self.pending_refreshes).items():
            #if (current_time - start_time) > 10*60:
                #del self.pending_refreshes[r]

        for library in d['MediaContainer']['Directory']:
            last_scan = library['scannedAt']
            library_type = library['type']
            # Don't do anything if the scan interval is zero
            if self.library_scan_interval[library_type] == 0: continue

            if not library['refreshing']:
                # If Plex is not currently refreshing
                if current_time - last_scan > self.library_scan_interval.get(library_type, 60*60*24):
                    # Library last refreshed earlier than library scan interval, so mark for refresh
                    if library['key'] not in self.pending_refreshes:
                        log.info(f'Starting refresh of {library["title"]}')
                        end_point = f'/library/sections/{library["key"]}/refresh'
                        j = self._json_query(end_point)
                        self.pending_refreshes[library['key']] = current_time
                    else:
                        # We've already queued this up for a refresh so don't do anything
                        pass
                else:
                    if library['key'] in self.pending_refreshes:
                        log.info(f'Completed refresh of {library["title"]}')
                        del self.pending_refreshes[library['key']]

def sigterm_handler(_signo, _stack_frame):
    print('SIGTERM received, plex_sleep exiting...')
    sys.exit(0)

if __name__ == '__main__':
    options = docopt.docopt(__doc__, version=__version__)

    log_level = logging.WARNING
    if options['-v']: log_level = logging.INFO
    if options['-d']: log_level = logging.DEBUG

    # Set up signal handler for graceful docker quitting
    signal.signal(signal.SIGTERM, sigterm_handler)

    logging.basicConfig(format="%(asctime)s — plex_sleep (%(levelname)s):%(name)s — %(message)s", level=log_level)
    p = PlexSleep(options['CONFIGFILE'])
