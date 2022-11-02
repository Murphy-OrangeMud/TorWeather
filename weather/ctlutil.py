import logging
import re
import string

import stem.version

from stem import Flag
from stem.control import Controller
from config import config

unparsable_email_file = 'log/unparsable_email.txt'

class CtlUtil:

    _CONTROL_HOST = '127.0.0.1'
    _CONTROL_PORT = config.control_port
    _AUTHENTICATOR = config.authenticator

    def __init__(self, control_host=_CONTROL_HOST,
                       control_port=_CONTROL_PORT,
                       sock=None,
                       authenticator=_AUTHENTICATOR):
        self.control_host = control_host
        self.control_port = control_port
        self.authenticator = authenticator

        try:
            self.control = Controller.from_port(port=self.control_host)
        except stem.SocketError, exc:
            logging.error("Unable to connect to tor's control port: %s" % exc)
            raise exc

        self.control.authenticate(config.authenticator)

    def __del__(self):
        self.control.close()

    def is_up(self, fingerprint):
        try:
            self.control.get_network_status(fingerprint)
            return True
        except:
            return False

    def is_exit(self, fingerprint):
        try:
            desc = self.control.get_server_descriptor(fingerprint)
            return desc.exit_policy.can_exit_to(port=80)
        except stem.ControllerError, exc:
            logging.error("Unable to get server descriptor for '%s': %s" % (fingerprint, exc))
            return False

    def get_finger_name_list(self):
        router_list = []

        for desc in self.control.get_server_descriptors([]):
            if desc.fingerprint:
                router_list.append((desc.fingerprint, desc.nickname))

        return router_list

    def is_stable(self, fingerprint):
        try:
            desc = self.control.get_network_status(fingerprint)
            return Flag.Stable in desc.flags
        except stem.ControllerError(e):
            return False

    def is_hibernating(self, fingerprint):
        try:
            desc = self.control.get_server_descriptor(fingerprint)
            return desc.hibernating
        except stem.ControllerError:
            return False

    def is_up_or_hibernating(self, fingerprint):
        return (self.is_up(fingerprint) or self.is_hibernating(fingerprint))

    def get_bandwidth(self, fingerprint):
        try:
            desc = self.control.get_server_descriptor(fingerprint)
            return desc.observed_bandwidth / 1000
        except stem.ControllerError:
            return 0

    def get_version(self, fingerprint):
        try:
            desc = self.control.get_server_descriptor(fingerprint)
            return str(desc.tor_version)
        except stem.ControllerError:
            return ''

    