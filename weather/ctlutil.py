import logging
import multiprocessing
import re
import string
import functools
import threading

import stem
import stem.version
import stem.response.events

from stem import Flag, StreamStatus, CircStatus
from stem.control import Controller
from config import config

import dns.resolver
from test import resolve_exit
import torsocks
import socket
import error

unparsable_email_file = 'log/unparsable_email.txt'

def get_source_port(self, stream_line):
    pattern = "SOURCE_ADDR=[0-9\.]{7,15}:([0-9]{1,5})"
    match = re.search(pattern, stream_line)

    if match:
        return int(match.group(1))

    return None


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
            self.control = Controller.from_port(port=self.control_port)
        except stem.SocketError:
            logging.error(
                "Unable to connect to tor's control port: %s" % self.control_port)
            raise Exception

        self.control.authenticate(config.authenticator)
        self.destinations = None
        self.domains = {
            "www.youporn.com": [],
            "youporn.com": [],
            "www.torproject.org": [],
            "www.i2p2.de": [],
            "torrentfreak.com": [],
            "blockchain.info": [],
        }

        for domain in list(self.domains.keys()):
            response = dns.resolver.resolve(domain)
            for record in response:
                logging.debug("Domain %s maps to %s." %
                              (domain, record.address))
                self.domains[domain].append(record.address)

        self.unattached = {}

        self.manager = None
        self.queue = None
        self.check_finished_lock = None

        # for dns
        self.already_finished = False

    def setup_task(self):

        self.manager = multiprocessing.Manager()
        self.queue = self.manager.Queue()
        self.check_finished_lock = threading.Lock()

        queue_thread = threading.Thread(target=self.queue_reader)
        queue_thread.daemon = False
        queue_thread.start()

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
            logging.error(
                "Unable to get server descriptor for '%s': %s" % (fingerprint, exc))
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

    def resolve_exit(self):  # TODO: whether add fingerprint
        sock = torsocks.torsocket()
        sock.settimeout(10)

        for domain in list(self.domains.keys()):
            try:
                ipv4 = sock.resolve(domain)
            except error.SOCKSv5Error as err:
                logging.debug("Exit relay %s could not resolve IPv4 address for "
                              "\"%s\" because: %s" % (exit, domain, err))
                return False
            except socket.timeout as err:
                logging.debug(
                    "Socket over exit relay %s timed out: %s" % (exit, err))
                return False
            except EOFError as err:
                logging.debug("EOF error: %s" % err)
                return False

            if ipv4 not in self.domains[domain]:
                logging.critical("Exit relay %s returned unexpected IPv4 address %s "
                                 "for domain %s" % (exit, ipv4, domain))
                return False
            else:
                logging.debug("IPv4 address of domain %s as expected for %s." %
                              (domain, exit))

        return True

    def new_event(self, event):
        if isinstance(event, stem.response.events.CircuitEvent):
            self.new_circuit(event)
        elif isinstance(event, stem.response.events.StreamEvent):
            self.new_stream(event)
        else:
            logging.warning("Received unexpected event %s." % str(event))

    def new_circuit(self, circ_event):
        if circ_event.status not in [CircStatus.BUILT]:
            return

        last_hop = circ_event.path[-1]
        exit_fingerprint = last_hop[0]
        logging.debug("Circuit for exit relay \"%s\" is built.  "
                      "Now invoking probing module." % exit_fingerprint)

        exit_desc = self.control.get_server_descriptor(exit_fingerprint)
        if exit_desc is None:
            self.control.close_circuit(circ_event.id)
            return

        def dns_detector():
            try:
                try:
                    with torsocks.MonkeyPatchedSocket(self.queue, circ_event.id, socks_port):
                        resolve_exit()
                except (error.SOCKSv5Error, socket.error) as err:
                    logging.info(err)
                
                logging.debug("Informing event handler that module finished.")
                self.queue.put((circ_event.id, None)) # TODO: what to put: the result of resolve_exit
            except KeyboardInterrupt:
                pass

        proc = multiprocessing.Process(target=dns_detector)
        proc.daemon = True
        proc.start()

    def new_stream(self, stream_event):
        if stream_event.status not in [StreamStatus.NEW, StreamStatus.NEWRESOLVE]:
            return

        port = get_source_port(str(stream_event))
        if not port:
            logging.warning("Couldn't extract source port from stream "
                        "event: %s" % str(stream_event))
            return
        
        logging.debug("Adding attacher for new stream %s." % stream_event.id)
        self.attach_stream_to_circuit_prepare(port, stream_id=stream_event.id)

    def attach_stream_to_circuit_prepare(self, port, circuit_id=None, stream_id=None):
        assert ((circuit_id is not None) and (stream_id is None)) or \
               ((circuit_id is None) and (stream_id is not None))

        if port in self.unattached:
            attach = self.unattached[port]

            if circuit_id:
                attach(circuit_id=circuit_id)
            else:
                attach(stream_id=stream_id)

            del self.unattached[port]
        else:
            if circuit_id:
                partially_attached = functools.partial(self._attach,
                                                       circuit_id=circuit_id)
                self.unattached[port] = partially_attached
            else:
                partially_attached = functools.partial(self._attach,
                                                       stream_id=stream_id)
                self.unattached[port] = partially_attached

        logging.debug("Pending attachers: %d." % len(self.unattached))

    def _attach(self, stream_id=None, circuit_id=None):
        logging.debug("Attempting to attach stream %s to circuit %s." %
                  (stream_id, circuit_id))

        try:
            self.control.attach_stream(stream_id, circuit_id)
        except stem.OperationFailed as err:
            logging.warning("Failed to attach stream because: %s" % err)

    def queue_reader(self):
        while True:
            try:
                circ_id, sockname = self.queue.get()
            except EOFError:
                logging.debug("IPC queue terminated.")
                break

            if sockname is None:
                logging.debug("Closing finished circuit %s." % circ_id)
                try:
                    self.control.close_circuit(circ_id)
                except stem.InvalidArguments as err:
                    logging.debug("Could not close circuit because: %s" % err)

                self.check_finished()
            else:
                logging.debug("Read from queue: %s, %s" % (circ_id, str(sockname)))
                port = int(sockname[1])
                self.attach_stream_to_circuit_prepare(port, circuit_id=circ_id)
                self.check_finished()

    def check_finished(self):
        with self.check_finished_lock:
            if self.already_finished:
                return

            # TODO: Fill in self.stats
            # Did all circuits either build or fail?
            circs_done = ((self.stats.failed_circuits +
                           self.stats.successful_circuits) ==
                          self.stats.total_circuits)

            # Was every built circuit attached to a stream?
            streams_done = (self.stats.finished_streams >=
                            (self.stats.successful_circuits -
                             self.stats.failed_circuits))

            logging.debug("failedCircs=%d, builtCircs=%d, totalCircs=%d, "
                      "finishedStreams=%d" % (self.stats.failed_circuits,
                                              self.stats.successful_circuits,
                                              self.stats.total_circuits,
                                              self.stats.finished_streams))

            if circs_done and streams_done:
                self.already_finished = True

                for proc in multiprocessing.active_children():
                    logging.debug("Terminating remaining PID %d." % proc.pid)
                    proc.terminate()

                logging.info(self.stats)
                return
