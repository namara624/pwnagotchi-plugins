import os
import logging
import re
import subprocess
import time
import random
from io import TextIOWrapper
from pwnagotchi import plugins

import pwnagotchi.ui.faces as faces
from pwnagotchi.bettercap import Client

from pwnagotchi.ui.components import Text,LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts

class Fix_BRCMF(plugins.Plugin):
    __author__ = 'xxx@xxx.xxx'
    __version__ = '0.1.0'
    __license__ = 'GPL3'
    __description__ = 'Reload brcmfmac module when blindbug is detected, instead of rebooting. Adapted from WATCHDOG.'
    __name__ = 'Fix_BRCMF'
    __help__ = """
    Reload brcmfmac module when blindbug is detected, instead of rebooting. Adapted from WATCHDOG.
    """
    __dependencies__ = {
        'pip': ['scapy']
    }
    __defaults__ = {
        'enabled': False,
    }

    def __init__(self):
        self.options = dict()
        self.pattern = re.compile(r'brcmf_cfg80211_nexmon_set_channel.*?Set Channel failed')
        self.pattern2 = re.compile(r'wifi error while hopping to channel')
        self.isReloadingMon0 = False
        self.connection = None
        self.LASTTRY = 0
        self._status = "--"
        self._count = 0

    def on_loaded(self):
        """
        Gets called when the plugin gets loaded
        """
        self.pattern = re.compile(r'brcmf_cfg80211_nexmon_set_channel.*?Set Channel failed')
        self._status = "ld"
        logging.info("[FixBRCMF] plugin loaded.")

    def on_ready(self, agent):
        try:
            cmd_output = subprocess.check_output("ip link show mon0", shell=True)
            logging.info("[FixBRCMF ip link show mon0]: %s" % repr(cmd_output))
            if ",UP," in str(cmd_output):
                logging.info("mon0 is up.");
                self._status = "up"
            last_lines = ''.join(list(TextIOWrapper(subprocess.Popen(['journalctl','-n10','-k'],
                                                                         stdout=subprocess.PIPE).stdout))[-10:])
            if len(self.pattern.findall(last_lines)) >= 3:
                self._status = "XX"
                if hasattr(agent, 'view'):
                    display = agent.view()
                    display.set('status', 'Blind-Bug detected. Restarting.')
                    display.update(force=True)
                logging.info('[FixBRCMF] Blind-Bug detected. Restarting.\n%s' % repr(last_lines))
                try:
                    self._tryTurningItOffAndOnAgain(agent)
                except Exception as err:
                    logging.warning("[FixBRCMF turnOffAndfOn] %s" % repr(err))
            else:
                logging.info("[FixBRCMF] Logs look good, too:\n%s" % (last_lines))
                self._status = ""

        except Exception as err:
            logging.error("[FixBRCMF ip link show mon0]: %s" % repr(err))
            try:
                self._status = "xx"
                self._tryTurningItOffAndOnAgain(agent)
            except Exception as err:
                logging.error("[FixBRCMF OffNOn]: %s" % repr(err))

    # bettercap sys_log event
    # search syslog events for the brcmf channel fail, and reset when it shows up
    # apparently this only gets messages from bettercap going to syslog, not from syslog
    def on_bcap_sys_log(self, agent, event):
        if re.search('wifi error while hopping to channel', event['data']['Message']):
            logging.info("[FixBRCMF]SYSLOG MATCH: %s" % event['data']['Message'])
            logging.info("[FixBRCMF]**** restarting wifi.recon")
            try:
                result = agent.run("wifi.recon off; wifi.recon on")
                if result["success"]:
                    logging.info("[FixBRCMF] wifi.recon flip: success!")
                    if hasattr(agent, 'view'):
                        display = agent.view()
                        if display: display.update(force=True, new_data={"status": "Wifi recon flipped!",
                                                                         "face":faces.COOL})
                    else: print("Wifi recon flipped")
                else:
                    logging.warning("[FixBRCMF] wifi.recon flip: FAILED: %s" % repr(result))
            except Exception as err:
                logging.error("[FixBRCMF]SYSLOG wifi.recon flip fail: %s" % err)

    def on_epoch(self, agent, epoch, epoch_data):
        # don't check if we ran a reset recently
        logging.debug("[FixBRCMF]**** epoch")
        if time.time() - self.LASTTRY > 180:
            # get last 10 lines
            display = None
            last_lines = ''.join(list(TextIOWrapper(subprocess.Popen(['journalctl','-n10','-k'],
                                                                     stdout=subprocess.PIPE).stdout))[-10:])
            other_last_lines = ''.join(list(TextIOWrapper(subprocess.Popen(['journalctl','-n10'],
                                                                           stdout=subprocess.PIPE).stdout))[-10:])
            logging.debug("[FixBRCMF]**** checking")
            if len(self.pattern.findall(last_lines)) >= 3:
                logging.info("[FixBRCMF]**** Should trigger a reload of the mon0 device:\n%s" % last_lines)
                if hasattr(agent, 'view'):
                    display = agent.view()
                    display.set('status', 'Blind-Bug detected. Restarting.')
                    display.update(force=True)
                logging.info('[FixBRCMF] Blind-Bug detected. Restarting.')
                try:
                    self._tryTurningItOffAndOnAgain(agent)
                except Exception as err:
                    logging.warn("[FixBRCMF] TTOAOA: %s" % repr(err))
            elif len(self.pattern2.findall(other_last_lines)) >= 5:
                if hasattr(agent, 'view'):
                    display = agent.view()
                    display.set('status', 'Wifi channel stuck. Restarting recon.')
                    display.update(force=True)
                logging.info('[FixBRCMF] Wifi channel stuck. Restarting recon.')

                try:
                    result = agent.run("wifi.recon off; wifi.recon on")
                    if result["success"]:
                        logging.info("[FixBRCMF] wifi.recon flip: success!")
                        if display: display.update(force=True, new_data={"status": "Wifi recon flipped!",
                                                                         "brcmfmac_status": self._status,
                                                                         "face":faces.COOL})
                        else: print("Wifi recon flipped\nthat was easy!")
                    else:
                        logging.warning("[FixBRCMF] wifi.recon flip: FAILED: %s" % repr(result))

                except Exception as err:
                    logging.error("[FixBRCMF wifi.recon flip] %s" % repr(err))

            else:
                print("logs look good")

    def logPrintView(self, level, message, ui=None, displayData=None, force=True):
        try:
            if level is "error":
                logging.error(message)
            elif level is "warning":
                logging.warning(message)
            elif level is "debug":
                logging.debug(message)
            else:
                logging.info(message)

            if ui: ui.update(force=force, new_data=displayData)
            elif displayData and "status" in displayData:
                print(displayData["status"])
            else:
                print("[%s] %s" % (level, message))
        except Exception as err:
            logging.error("[logPrintView] ERROR %s" % repr(err))

    def _tryTurningItOffAndOnAgain(self, connection):
        # avoid overlapping restarts, but allow it if its been a while
        # (in case the last attempt failed before resetting "isReloadingMon0")
        if self.isReloadingMon0 and (time.time() - self.LASTTRY) < 180:
            logging.info("[FixBRCMF] Duplicate attempt ignored")
        else:
            self.isReloadingMon0 = True
            self.LASTTRY = time.time()

            self._status = "BL"
            if hasattr(connection, 'view'):
                display = connection.view()
                if display: display.update(force=True, new_data={"status": "I'm blind! Try turning it off and on again",
                                                                 "brcmfmac_status": self._status,
                                                                 "face":faces.BORED})
            else:
                display = None

            # main divergence from WATCHDOG starts here
            #
            # instead of rebooting, and losing all that energy loading up the AI
            #    pause wifi.recon, close mon0, reload the brcmfmac kernel module
            #    then recreate mon0, ..., and restart wifi.recon

            # Turn it off

            # attempt a sanity check. does mon0 exist?
            # is it up?
            try:
                cmd_output = subprocess.check_output("ip link show mon0", shell=True)
                logging.info("[FixBRCMF ip link show mon0]: %s" % repr(cmd_output))
                if ",UP," in str(cmd_output):
                    logging.info("mon0 is up. Skip reset?");
                    #not reliable, so don't skip just yet
                    #print("mon0 is up. Skipping reset.");
                    #self.isReloadingMon0 = False
                    #return
            except Exception as err:
                logging.error("[FixBRCMF ip link show mon0]: %s" % repr(err))

            try:
                result = connection.run("wifi.recon off")
                if "success" in result:
                    self.logPrintView("info", "[FixBRCMF] wifi.recon off: %s!" % repr(result),
                                      display, {"status": "Wifi recon paused!", "face":faces.COOL})
                    time.sleep(2)
                else:
                    self.logPrintView("warning", "[FixBRCMF] wifi.recon off: FAILED: %s" % repr(result),
                                      display, {"status": "Recon was busted (probably)",
                                                "face":random.choice((faces.BROKEN, faces.DEBUG))})
            except Exception as err:
                logging.error("[FixBRCMF wifi.recon off] error  %s" % (repr(err)))

            logging.info("[FixBRCMF] recon paused. Now trying mon0 reload")

            try:
                cmd_output = subprocess.check_output("sudo ifconfig mon0 down && sudo iw dev mon0 del", shell=True)
                self._status = "dn"
                self.logPrintView("info", "[FixBRCMF] mon0 down and deleted: %s" % cmd_output,
                                  display, {"status": "mon0 d-d-d-down!", "face":faces.BORED})
            except Exception as nope:
                logging.error("[FixBRCMF delete mon0] %s" % nope)
                pass

            logging.debug("[FixBRCMF] Now trying modprobe -r")

            # Try this sequence 3 times until it is reloaded
            #
            # Future: while "not fixed yet": blah blah blah. if "max_attemts", then reboot like the old days
            #
            tries = 0
            while tries < 3:
                try:
                    # unload the module
                    cmd_output = subprocess.check_output("sudo modprobe -r brcmfmac", shell=True)
                    self.logPrintView("info", "[FixBRCMF] unloaded brcmfmac", display,
                                 {"status": "Turning it off #%d" % tries, "face":faces.SMART})
                    self._status = "ul"
                    time.sleep(1 + tries)

                    # reload the module
                    try:
                        # reload the brcmfmac kernel module
                        cmd_output = subprocess.check_output("sudo modprobe brcmfmac", shell=True)

                        self.logPrintView("info", "[FixBRCMF] reloaded brcmfmac")
                        self._status = "rl"
                        time.sleep(10 + 4 * tries) # give it some time for wlan device to stabilize, or whatever

                        # success! now make the mon0
                        try:
                            cmd_output = subprocess.check_output("sudo iw phy \"$(iw phy | head -1 | cut -d' ' -f2)\" interface add mon0 type monitor && sudo ifconfig mon0 up", shell=True)
                            self.logPrintView("info", "[FixBRCMF interface add mon0] worked #%d: %s" % (tries, cmd_output))
                            self._status = "up"
                            time.sleep(tries + 5)
                            try:
                                # try accessing mon0 in bettercap
                                result = connection.run("set wifi.interface mon0")
                                if "success" in result:
                                    logging.info("[FixBRCMF set wifi.interface mon0] worked: %s" % repr(result))
                                    self._status = ""
                                    self._count = self._count + 1
                                    time.sleep(1)
                                    # stop looping and get back to recon
                                    break
                                else:
                                    logging.info("[FixBRCMF set wifi.interfaceface mon0] failed? %s" % repr(result))
                            except Exception as err:
                                logging.info("[FixBRCMF set wifi.interface mon0] except: %s" % (repr(result), repr(err)))
                        except Exception as cerr: #
                            if not display: print("failed loading mon0 attempt #%d: %s" % (tries, repr(cerr)))
                    except Exception as err: # from modprobe
                        if not display: print("Failed reloading brcmfmac")
                        logging.error("[FixBRCMF] Failed reloading brcmfmac %s" % repr(err))


                except Exception as nope: # from modprobe -r
                    # fails if already unloaded, so probably fine
                    logging.error("[FixBRCMF #%d modprobe -r] %s" % (tries, repr(nope)))
                    if not display: print("[FixBRCMF #%d modprobe -r] %s" % (tries, repr(nope)))
                    pass

                tries = tries + 1
                if tries < 3:
                    logging.info("[FixBRCMF] mon0 didn't make it. trying again")
                    if not display: print(" mon0 didn't make it. trying again")

            # exited the loop, so hopefully it loaded
            if tries < 3:
                if display: display.update(force=True, new_data={"status": "And back on again...",
                                                                 "brcmfmac_status": self._status,
                                                                 "face":faces.INTENSE})
                else: print("And back on again...")
                logging.info("[FixBRCMF] mon0 back up")
            else:
                self.LASTTRY = time.time()

            time.sleep(8 + tries * 2) # give it a bit before restarting recon in bettercap
            self.isReloadingMon0 = False

            logging.info("[FixBRCMF] re-enable recon")
            try:
                result = connection.run("wifi.clear; wifi.recon on")

                if "success" in result: # and result["success"] is True:
                    self._status = ""
                    if display: display.update(force=True, new_data={"status": "I can see again! (probably): %s" % repr(result),
                                                                     "brcmfmac_status": self._status,
                                                                     "face":faces.HAPPY})
                    else: print("I can see again")
                    logging.info("[FixBRCMF] wifi.recon on %s" % repr(result))
                    self.LASTTRY = time.time() + 120 # 2 minute pause until next time.
                else:
                    logging.error("[FixBRCMF] wifi.recon did not start up: %s" % repr(result))
                    self.LASTTRY = time.time() - 300 # failed, so try again ASAP
                    self.isReloadingMon0 = False

            except Exception as err:
                logging.error("[FixBRCMF wifi.recon on] %s" % repr(err))

    # called to setup the ui elements
    def on_ui_setup(self, ui):
        # add custom UI elements
        if "position" in self.options:
            pos = self.options['position'].split(',')
            pos = [int(x.strip()) for x in pos]
        else:
            pos = (ui.width()/2+35,ui.height()-11)

        logging.info("Got here")
        ui.add_element('brcmfmac_status', Text(color=BLACK, value='--', position=pos, font=fonts.Small))

        # called when the ui is updated
    def on_ui_update(self, ui):
        # update those elements
        if self._status:
            ui.set('brcmfmac_status', "mon0 %s" % self._status)
        else:
            ui.set('brcmfmac_status', "rst#%s" % self._count)

    def on_unload(self, ui):
        try:
            ui.remove_element('brcmfmac_status')
            logging.info("[FixBRCMF] unloaded")
        except Exception as err:
            logging.info("[FixBRCMF] unload err %s " % repr(err))
        pass

# run from command line to brute force a reload
if __name__ == "__main__":
    print("Performing brcmfmac reload and restart mon0 in 5 seconds...")
    fb =  Fix_BRCMF()

    data = {'Message': "kernel: brcmfmac: brcmf_cfg80211_nexmon_set_channel: Set Channel failed: chspec=1234"}
    event = {'data': data}


    agent = Client('localhost', port=8081, username="pwnagotchi", password="pwnagotchi");

    time.sleep(2)
    print("3 seconds")
    time.sleep(3)
    #fb.on_epoch(agent, event, None)
    fb._tryTurningItOffAndOnAgain(agent)

