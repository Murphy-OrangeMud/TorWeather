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
import stem.process
from config import config

from datetime import datetime
import dns.resolver
import torsocks
import socket
import error
from model import hours_since

log = logging.getLogger(__name__)


def parse_log_lines(ports, log_line):
    """
    Extract the SOCKS and control port from Tor's log output.

    Both ports are written to the given dictionary.
    """

    log.debug("Tor says: %s" % log_line)

    if re.search(r"^.*Bootstrapped \d+%.*$", log_line):
        log.info(re.sub(r"^.*(Bootstrapped \d+%.*)$", r"Tor \1", log_line))

    socks_pattern = "Socks listener listening on port ([0-9]{1,5})."
    control_pattern = "Control listener listening on port ([0-9]{1,5})."

    match = re.search(socks_pattern, log_line)
    if match:
        ports["socks"] = int(match.group(1))
        log.debug("Tor uses port %d as SOCKS port." % ports["socks"])

    match = re.search(control_pattern, log_line)
    if match:
        ports["control"] = int(match.group(1))
        log.debug("Tor uses port %d as control port." % ports["control"])


def bootstrap():
        ports = {}
        partial_parse_log_lines = functools.partial(parse_log_lines, ports)
        try:
            proc = stem.process.launch_tor_with_config(
                config={
                    "SOCKSPort": "auto",
                    "ControlPort": "auto",
                    "DataDirectory": "/tmp/exitmap_tor_datadir",
                    "CookieAuthentication": "1",
                    "LearnCircuitBuildTimeout": "0",
                    "CircuitBuildTimeout": "40",
                    "__DisablePredictedCircuits": "1",
                    "__LeaveStreamsUnattached": "1",
                    "FetchHidServDescriptors": "0",
                    "UseMicroDescriptors": "0",
                    "PathsNeededToBuildCircuits": "0.95",
                },
                timeout=300,
                take_ownership=True,
                completion_percent=75,
                init_msg_handler=partial_parse_log_lines,
            )
            log.debug("Successfully started Tor process (PID=%d)." % proc.pid)
        except OSError as err:
            log.debug("Couldn't launch Tor: %s.  Maybe try again?" % err)
            return None, None

        return ports["socks"], ports["control"]


unparsable_email_file = 'log/unparsable_email.txt'


def get_source_port(stream_line):
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
        self.sock_port = None
        self.control_port = control_port
        self.authenticator = authenticator
        self.control = None

        try:
            #self.sock_port, self.control_port = bootstrap()
            log.debug("Bootstrapped!")
            #assert self.sock_port is not None
            #self.control = Controller.from_port(port=self.control_port)
        except stem.SocketError:
            log.debug(
                "Unable to connect to tor's control port: %s" % self.control_port)
            raise Exception

        #self.control.authenticate(self.authenticator)

        log.debug("Redirecting Tor's logging to /dev/null.")
        #self.control.set_conf("Log", "err file /dev/null")

        self.cached_concensus_path = "/tmp/exitmap_tor_datadir/cached-consensus"

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
                log.debug("Domain %s maps to %s." %
                          (domain, record.address))
                self.domains[domain].append(record.address)

        self.unattached = {}

        self.manager = None
        self.queue = None
        self.check_finished_lock = None
        self.queue_thread = None

        # for dns
        self.already_finished = False
        self.finished_streams = 0
        self.total_circuits = 0
        self.failed_circuits = 0
        self.successful_circuits = 0

        self.bandwidths = {}
        self.consensus = None
        self.last_updated_time = datetime.now()

        self.dns_email_list = []
        # self.update_finger_name_list()

    def setup_task(self):
        self.manager = multiprocessing.Manager()
        self.queue = self.manager.Queue()
        self.check_finished_lock = threading.Lock()

        self.queue_thread = threading.Thread(target=self.queue_reader)
        self.queue_thread.daemon = False
        self.queue_thread.start()

    def __del__(self):
        if self.control is not None:
            self.control.close()

    def is_exit(self, fingerprint):
        """
        if hours_since(self.last_updated_time) > 2:
            self.update_finger_name_list()
        for fpr, relay in self.consensus.routers.items():
            if fingerprint == fpr:
                return relay.exit_policy.is_exiting_allowed()

        return False
        """
        # because we cached consensus locally
        # when bootstrap tor network it's unneceessary to fetch

        for desc in stem.descriptor.parse_file(self.cached_concensus_path, validate=False):
            if desc.fingerprint == fingerprint:
                return desc.exit_policy.is_exiting_allowed()

        return False

    def is_bad_exit(self, fingerprint):
        for desc in stem.descriptor.parse_file(self.cached_concensus_path, validate=False):
            if desc.fingerprint == fingerprint and desc.exit_policy.is_exiting_allowed():
                if stem.Flag.BADEXIT in desc.flags:
                    return True
                else:
                    return False

        raise Exception("Not an exit")

    def get_finger_name_list(self):
        """
        if hours_since(self.last_updated_time) > 2:
            self.update_finger_name_list()

        router_list = []
        for fingerprint, relay in self.consensus.routers.items():
            router_list.append(fingerprint)
        return router_list
        """
        # because we cached consensus locally
        # when bootstrap tor network it's unneceessary to fetch

        router_list = []
        name_list = []
        for desc in stem.descriptor.parse_file(self.cached_concensus_path):
            router_list.append(desc.fingerprint)
            name_list.append(desc.nickname)
        return router_list, name_list

    def update_finger_name_list(self):
        downloader = stem.descriptor.remote.DescriptorDownloader()
        consensus = downloader.get_consensus(
            document_handler=stem.descriptor.DocumentHandler.DOCUMENT).run()[0]
        self.consensus = consensus
        self.last_updated_time = datetime.now()

    def is_stable(self, fingerprint):
        """
        if hours_since(self.last_updated_time) > 2:
            self.update_finger_name_list()

        for fpr, relay in self.consensus.routers.items():
            if fpr == fingerprint:
                if 'Stable' in relay.flags:
                    return True
        return False
        """

        for desc in stem.descriptor.parse_file(self.cached_concensus_path):
            if fingerprint == desc.fingerprint:
                if stem.Flag.STABLE in desc.flags:
                    return True
                else:
                    return False

        return False

    def get_bandwidth(self, fingerprint):
        try:
            return self.bandwidths[fingerprint]
        except KeyError:
            return -1

    def get_bandwidths(self):
        try:
            desc = stem.descriptor.remote.get_bandwidth_file().run()[0]
            for fingerprint, measurement in desc.measurements.items():
                bandwidth = int(measurement.get('bw', 0))
                self.bandwidths[fingerprint] = bandwidth
        except Exception as e:
            log.warning("Failed to get bandwidths!", e)

    def get_version_type(self, fingerprint):
        log.debug("get_version_type")
        version_list = self.control.get_info(
            "status/version/recommended", "").split(',')
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

    def get_relay_desc(self, fingerprint):
        try:
            self.update_finger_name_list()

            for fpr, relay in self.consensus.routers.items():
                if fpr == fingerprint:
                    return relay
        except:
            log.warning("Failed to get updated relay descriptors")
            return None

    def resolve_exit(self):
        sock = torsocks.torsocket()
        sock.settimeout(10)

        for domain in list(self.domains.keys()):
            try:
                ipv4 = sock.resolve(domain)
            except error.SOCKSv5Error as err:
                log.debug("Exit relay %s could not resolve IPv4 address for "
                          "\"%s\" because: %s" % (exit, domain, err))
                return False
            except socket.timeout as err:
                log.debug(
                    "Socket over exit relay %s timed out: %s" % (exit, err))
                return False
            except EOFError as err:
                log.debug("EOF error: %s" % err)
                return False

            if ipv4 not in self.domains[domain]:
                log.critical("Exit relay %s returned unexpected IPv4 address %s "
                             "for domain %s" % (exit, ipv4, domain))
                return False
            else:
                log.debug("IPv4 address of domain %s as expected for %s." %
                          (domain, exit))

        return True

    def new_event(self, event):
        if isinstance(event, stem.response.events.CircuitEvent):
            self.new_circuit(event)
        elif isinstance(event, stem.response.events.StreamEvent):
            self.new_stream(event)
        else:
            log.warning("Received unexpected event %s." % str(event))

    def new_circuit(self, circ_event):
        log.debug("Provoke new circuit handler")
        if circ_event.status in [CircStatus.FAILED]:
            log.debug("Circuit failed because: %s" % str(circ_event.reason))
            self.failed_circuits += 1
        elif circ_event.status in [CircStatus.BUILT]:
            self.successful_circuits += 1

        self.check_finished()

        if circ_event.status not in [CircStatus.BUILT]:
            return

        last_hop = circ_event.path[-1]
        exit_fingerprint = last_hop[0]
        log.debug("Circuit for exit relay \"%s\" is built.  "
                  "Now invoking probing module." % exit_fingerprint)

        desc = self.get_relay_desc(exit_fingerprint)
        if desc is None:
            self.control.close_circuit(circ_event.id)
            self.queue.put((circ_event.id, None, False, exit_fingerprint))
            return

        def dns_detector():
            flag = False
            try:
                with torsocks.MonkeyPatchedSocket(self.queue, circ_event.id):
                    flag = self.resolve_exit()
            except (error.SOCKSv5Error, socket.error) as err:
                log.info(err)
            except KeyboardInterrupt:
                pass
            finally:
                log.debug("Informing event handler that module finished.")
                self.queue.put((circ_event.id, None, flag, exit_fingerprint))

        proc = multiprocessing.Process(target=dns_detector)
        proc.daemon = True
        proc.start()

    def new_stream(self, stream_event):
        log.debug("Provoke new stream handler")
        if stream_event.status not in [StreamStatus.NEW, StreamStatus.NEWRESOLVE]:
            return

        port = get_source_port(str(stream_event))
        if not port:
            log.warning("Couldn't extract source port from stream "
                        "event: %s" % str(stream_event))
            return

        log.debug("Adding attacher for new stream %s." % stream_event.id)
        self.attach_stream_to_circuit_prepare(port, stream_id=stream_event.id)
        self.check_finished()

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

        log.debug("Pending attachers: %d." % len(self.unattached))

    def _attach(self, stream_id=None, circuit_id=None):
        log.debug("Attempting to attach stream %s to circuit %s." %
                  (stream_id, circuit_id))

        try:
            self.control.attach_stream(stream_id, circuit_id)
        except stem.OperationFailed as err:
            log.warning("Failed to attach stream because: %s" % err)

    def queue_reader(self):
        fingerprint_list = []
        while True:
            try:
                circ_id, sockname, flag, exit_fingerprint = self.queue.get()
            except EOFError:
                log.debug("IPC queue terminated.")
                break

            if sockname is None:
                log.debug("Closing finished circuit %s." % circ_id)
                if flag == False:
                    fingerprint_list.append(exit_fingerprint)
                try:
                    self.control.close_circuit(circ_id)
                except stem.InvalidArguments as err:
                    log.debug("Could not close circuit because: %s" % err)

                self.finished_streams += 1
                self.check_finished()
            else:
                log.debug("Read from queue: %s, %s" % (circ_id, str(sockname)))
                port = int(sockname[1])
                self.attach_stream_to_circuit_prepare(port, circuit_id=circ_id)
                self.check_finished()

            if self.already_finished:
                break

        self.dns_email_list = fingerprint_list
        return

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

            log.debug("failedCircs=%d, builtCircs=%d, totalCircs=%d, "
                      "finishedStreams=%d" % (self.failed_circuits,
                                              self.successful_circuits,
                                              self.total_circuits,
                                              self.finished_streams))

            if circs_done and streams_done:
                self.already_finished = True

                for proc in multiprocessing.active_children():
                    log.debug("Terminating remaining PID %d." % proc.pid)
                    proc.terminate()

                return

    def finished(self):
        self.queue_thread.join()
        return self.dns_email_list
