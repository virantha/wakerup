"""WakerUp

Usage:
    wakerup.py [-hdv] CONFIGFILE

Read in a list of hosts to wake up in the CONFIGFILE and a log
file to watch for a specified regex.


Arguments:
    CONFIGFILE      configuration file

Options:
    -h --help 
    -v          Print out information as it runs
    -d          Debug information

"""
import time, os, re, sys, logging
import docopt, yaml
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from wakeonlan import send_magic_packet
from pythonping import ping

log = logging.getLogger(__name__)

class WakerUp:
    DEFAULT_INTERVAL = 5  # Minimum time to wait before resending a etherwake packet
    #def __init__(self, filename, regex, mac_addr):
    def __init__(self, config_filename):
        self._load_config(config_filename)

        self.create_event_handler()
        self.start_observer()

    def _load_config(self, config_filename):
        with open(config_filename) as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
        self.config = config
        for name, wakeup_rule in self.config.items():
            # Precomiple the regexes and replace them in the dict
            wakeup_rule['regex'] = re.compile(wakeup_rule['regex'])
            # Convert paths to absolute paths
            wakeup_rule['log_filename'] = os.path.abspath(wakeup_rule['log_filename'])
            filename = wakeup_rule['log_filename'] 
            if os.path.isfile(filename):
                wakeup_rule['file_handle'] = open(filename, 'r')
                log.debug(f'Seeking to end of {filename}')
                wakeup_rule['file_handle'].seek(0, 2)   # Seek to end of file
            else:
                wakeup_rule['file_handle'] = None
            # 
            wakeup_rule['last_wake_packet'] = 0

        log.debug (self.config)

    def create_event_handler(self):
        for rule_name, rule in self.config.items():
            rule['event_handler'] = WakeupEventHandler(self, rule_name, rule, '*.log', "", True, True)

    def start_observer(self):
        observer = Observer()
        for rule_name, rule in self.config.items():
            path = os.path.dirname(rule['log_filename'])
            observer.schedule(rule['event_handler'], path, recursive=False) 
            log.info(f'starting observer for {rule_name}')
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            observer.join()

    def file_created(self, name):
        self.config[name]['file_handle'] = open(self.config[name]['log_filename'], 'r')
        #self.file_handle = open(self.filename, 'r')
        self.get_lines(name)

    def file_invalidate(self, name):
        self.config[name]['file_handle'].close()
        self.config[name]['file_handle'] = None

    def get_lines(self, name):
        config = self.config[name]
        for line in config['file_handle']:
            log.debug(line.strip())
            if config['regex'].search(line):
                log.debug(f'Matched rule {name}')
                self.send_wake_packet(config)

    def send_wake_packet(self, config):
        n = time.time()
        interval = int(n - config['last_wake_packet'])
        # Need to check if host is already awake; if it is, then don't bother sending packet

        if interval > config['min_interval']:
            if self.is_awake(config['ip']):
                log.debug(f'{config["mac_addr"]} is alive at {config["ip"]} - not sending wol')
            else:
                log.info(f"Sending magic packet to {config['mac_addr']}")
                send_magic_packet(config['mac_addr'])
                config['last_wake_packet'] = time.time()
        else:
            log.debug(f'Sent magic packet {interval} seconds ago, so not sending again')

    def is_awake(self, host):
        r = ping(host, count=1, timeout=0.1)    
        return r.success()


class WakeupEventHandler(PatternMatchingEventHandler):

    def __init__(self, dispatch, wakeup_rule_name, wakeup_rule, patterns=None, ignore_patterns=None,
                 ignore_directories=False, case_sensitive=False):

        super(WakeupEventHandler, self).__init__(patterns, ignore_patterns, ignore_directories, case_sensitive)
        self.wakeup = dispatch
        self.wakeup_rule = wakeup_rule
        self.wakeup_rule_name = wakeup_rule_name

    def _this_file(self, event):
        if event.src_path == self.wakeup_rule['log_filename']:
            return True
        else:
            return False

    def on_created(self, event):
        if self._this_file(event):
            log.debug(f'{event.src_path} has been created')
            self.wakeup.file_created(self.wakeup_rule_name)

    def on_modified(self, event):
        if self._this_file(event):
            log.debug(f'{event.src_path} has been modified')
            self.wakeup.get_lines(self.wakeup_rule_name)

    def on_deleted(self, event):
        if self._this_file(event):
            log.debug(f'{event.src_path} has been deleted')
            self.wakeup.file_invalidate(self.wakeup_rule_name)
        
    def on_moved(self, event):
        if self._this_file(event):
            log.debug(f'{event.src_path} has been moved to {event.dest_path}')
            self.wakeup.file_invalidate(self.wakeup_rule_name)


if __name__ == '__main__':
    options = docopt.docopt(__doc__)

    log_level = logging.WARNING
    if options['-v']: log_level = logging.INFO
    if options['-d']: log_level = logging.DEBUG
    logging.basicConfig(format="%(asctime)s — wakerup (%(levelname)s):%(name)s — %(message)s", level=log_level)

    wakerup = WakerUp(options['CONFIGFILE'])