from ast import Pass
import logging
import multiprocessing
from multiprocessing.sharedctypes import Value
import re
import string
import functools
import threading

import stem
import stem.version
import stem.response.events
import stem.descriptor
import stem.descriptor.remote

from stem import Flag, StreamStatus, CircStatus
from stem.control import Controller
from config import config

from datetime import datetime
import dns.resolver
import torsocks
import socket
import error
from model import hours_since

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

        self.control.authenticate(self.authenticator)
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
        self.finished_streams = 0
        self.total_circuits = 0
        self.failed_circuits = 0
        self.successful_circuits = 0

        self.bandwidths = {}
        self.consensus = None
        self.last_updated_time = datetime.now()
        self.update_finger_name_list()

    def setup_task(self):
        self.manager = multiprocessing.Manager()
        self.queue = self.manager.Queue()
        self.check_finished_lock = threading.Lock()

        queue_thread = threading.Thread(target=self.queue_reader)
        queue_thread.daemon = False
        queue_thread.start()

    def __del__(self):
        self.control.close()

    def is_exit(self, fingerprint):
        if hours_since(self.last_updated_time) > 2:
            self.update_finger_name_list()
        for fpr, relay in self.consensus.routers.items():
            if fingerprint == fpr:
                return relay.exit_policy.is_exiting_allowed()
        
        return False

    def get_finger_name_list(self):
        if hours_since(self.last_updated_time) > 2:
            self.update_finger_name_list()

        router_list = []
        for fingerprint, relay in self.consensus.routers.items():
            router_list.append((fingerprint, relay.nickname))
        return router_list

    def update_finger_name_list(self):
        downloader = stem.descriptor.remote.DescriptorDownloader()
        consensus = downloader.get_consensus(document_handler=stem.descriptor.DocumentHandler.DOCUMENT).run()[0]
        self.consensus = consensus
        self.last_updated_time = datetime.now()
        
    def is_stable(self, fingerprint):
        if hours_since(self.last_updated_time) > 2:
            self.update_finger_name_list()

        for fpr, relay in self.consensus.routers.items():
            if fpr == fingerprint:
                if 'Stable' in relay.flags:
                    return True
        return False

    def get_bandwidth(self, fingerprint):
        try:
            return self.bandwidths[fingerprint]
        except KeyError:
            return -1

    def get_bandwidths(self):
        try:
            desc = stem.descriptor.remote.get_bandwidth_file().run()[0]
            for fingerprint, measurement in desc.measurement.items():
                bandwidth = int(measurement.get('bw', 0))
                self.bandwidths[fingerprint] = bandwidth
        except Exception as e:
            logging.warning("Failed to get bandwidths!", e)

    def get_version_type(self, fingerprint):
        print("get_version_type")
        version_list = self.control.get_info("status/version/recommended", "").split(',')
        client_version = self.control.get_version(fingerprint)

        if client_version == '':
            return 'ERROR'

        if not version_list:
            return 'RECOMMENDED'

        if client_version in version_list:
            return 'RECOMMENDED'

        if client_version.endswith("-dev"):
            version_list.append(client_version)
            if self.get_highest_version(version_list) == client_version:
                return 'RECOMMENDED'

            nondev_name = client_version.replace("-dev", "")
            if nondev_name in version_list:
                return 'RECOMMENDED'

        return 'OBSOLETE'

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
        if circ_event.status in [CircStatus.FAILED]:
            self.failed_circuits += 1
        elif circ_event.status in [CircStatus.BUILT]:
            self.successful_circuits += 1
        
        self.check_finished()

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
            flag = False
            try:
                try:
                    with torsocks.MonkeyPatchedSocket(self.queue, circ_event.id):
                        flag = self.resolve_exit()
                except (error.SOCKSv5Error, socket.error) as err:
                    logging.info(err)
                
                logging.debug("Informing event handler that module finished.")
                self.queue.put((circ_event.id, None, flag, exit_fingerprint)) # TODO: what to put: the result of resolve_exit
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
        fingerprint_list = []
        while True:
            try:
                circ_id, sockname, flag, exit_fingerprint = self.queue.get()
            except EOFError:
                logging.debug("IPC queue terminated.")
                break

            if sockname is None:
                logging.debug("Closing finished circuit %s." % circ_id)
                if flag == False:
                    fingerprint_list.append(exit_fingerprint)
                try:
                    self.control.close_circuit(circ_id)
                except stem.InvalidArguments as err:
                    logging.debug("Could not close circuit because: %s" % err)
                
                self.finished_streams += 1
                self.check_finished()
            else:
                logging.debug("Read from queue: %s, %s" % (circ_id, str(sockname)))
                port = int(sockname[1])
                self.attach_stream_to_circuit_prepare(port, circuit_id=circ_id)
                self.check_finished()

            if self.already_finished:
                break
        
        return fingerprint_list

    def check_finished(self):
        with self.check_finished_lock:
            if self.already_finished:
                return

            # Did all circuits either build or fail?
            circs_done = ((self.failed_circuits +
                           self.successful_circuits) ==
                          self.total_circuits)

            # Was every built circuit attached to a stream?
            streams_done = (self.finished_streams >=
                            (self.successful_circuits -
                             self.failed_circuits))

            logging.debug("failedCircs=%d, builtCircs=%d, totalCircs=%d, "
                      "finishedStreams=%d" % (self.failed_circuits,
                                              self.successful_circuits,
                                              self.total_circuits,
                                              self.finished_streams))

            if circs_done and streams_done:
                self.already_finished = True

                for proc in multiprocessing.active_children():
                    logging.debug("Terminating remaining PID %d." % proc.pid)
                    proc.terminate()

                return

