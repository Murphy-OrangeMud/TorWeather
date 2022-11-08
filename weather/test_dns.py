import time
from stem.control import Controller, EventType
import torsocks
import error
import logging
import dns.resolver
import socket
from stem import StreamStatus, CircStatus
import stem.descriptor.remote
import re
import stem
import random
import sys
import stem.process
import functools
import multiprocessing
import threading

log = logging.getLogger(__name__)

domains = {
    "www.youporn.com": [],
    "youporn.com": [],
    "www.torproject.org": [],
    "www.i2p2.de": [],
    "torrentfreak.com": [],
    "blockchain.info": [],
}
unattached = {}

controller = None
consensus = None
manager = None
queue = None
check_finished_lock = None

def get_exits():
    router_list = []
    for fingerprint, relay in consensus.routers.items():
        if relay.exit_policy.is_exiting_allowed():
            router_list.append(fingerprint)
    return router_list

def update_finger_name_list():
    global consensus
    downloader = stem.descriptor.remote.DescriptorDownloader()
    consensus = downloader.get_consensus(document_handler=stem.descriptor.DocumentHandler.DOCUMENT).run()[0]

def get_finger_name_list():
    router_list = []
    for fingerprint, relay in consensus.routers.items():
        router_list.append(fingerprint)
    return router_list

def get_source_port(stream_line):
    pattern = "SOURCE_ADDR=[0-9\.]{7,15}:([0-9]{1,5})"
    match = re.search(pattern, stream_line)

    if match:
        return int(match.group(1))

    return None

def setup():
    for domain in list(domains.keys()):
        response = dns.resolver.resolve(domain)
        for record in response:
            log.debug("Domain %s maps to %s." % (domain, record.address))
            domains[domain].append(record.address)

def setup_task():
    global manager, queue, check_finished_lock
    manager = multiprocessing.Manager()
    queue = manager.Queue()
    check_finished_lock = threading.Lock()

    queue_thread = threading.Thread(target=queue_reader)
    queue_thread.daemon = False
    queue_thread.start()

def queue_reader():
        while True:
            try:
                circ_id, sockname, flag, exit_fingerprint = queue.get()
            except EOFError:
                logging.debug("IPC queue terminated.")
                break

            if sockname is None:
                logging.debug("Closing finished circuit %s." % circ_id)
                print("Queue Reader: ", flag)
                try:
                    controller.close_circuit(circ_id)
                except stem.InvalidArguments as err:
                    logging.debug("Could not close circuit because: %s" % err)
                
            else:
                logging.debug("Read from queue: %s, %s" % (circ_id, str(sockname)))
                port = int(sockname[1])
                attach_stream_to_circuit_prepare(port, circuit_id=circ_id)        

def print_bw(event):
    print("Send: %i, Receive: %i" % (event.written, event.read))

def new_circuit(circ_event):
    print("Listener: new circuit")
    if circ_event.status not in [CircStatus.BUILT]:
        return

    last_hop = circ_event.path[-1]
    exit_fingerprint = last_hop[0]
    log.debug("Circuit for exit relay \"%s\" is built.  "
                      "Now invoking probing module." % exit_fingerprint)

    try:
        with torsocks.MonkeyPatchedSocket(None, circ_event.id, socks_port):
            print(resolve_exit())
    except (error.SOCKSv5Error, socket.error) as err:
        log.info(err)
    except KeyboardInterrupt:
        pass
    finally:
        log.debug("Informing event handler that module finished.")

def new_stream(stream_event):
    print("Listener: new stream")
    if stream_event.status not in [StreamStatus.NEW, StreamStatus.NEWRESOLVE]:
            return

    port = get_source_port(str(stream_event))
    if not port:
        log.warning("Couldn't extract source port from stream "
                        "event: %s" % str(stream_event))
        return
        
    log.debug("Adding attacher for new stream %s." % stream_event.id)
    attach_stream_to_circuit_prepare(port, stream_id=stream_event.id)

def attach_stream_to_circuit_prepare(port, circuit_id=None, stream_id=None):
    print("Attach stream to circuit prepare")
    assert ((circuit_id is not None) and (stream_id is None)) or \
               ((circuit_id is None) and (stream_id is not None))

    if port in unattached:
        attach = unattached[port]

        if circuit_id:
            attach(circuit_id=circuit_id)
        else:
            attach(stream_id=stream_id)

        del unattached[port]
    else:
        if circuit_id:
            partially_attached = functools.partial(_attach,
                                                       circuit_id=circuit_id)
            unattached[port] = partially_attached
        else:
            partially_attached = functools.partial(_attach,
                                                       stream_id=stream_id)
            unattached[port] = partially_attached

        log.debug("Pending attachers: %d." % len(unattached))

def _attach(stream_id=None, circuit_id=None):
    print("Attach")
    log.debug("Attempting to attach stream %s to circuit %s." %
                  (stream_id, circuit_id))

    try:
        controller.attach_stream(stream_id, circuit_id)
    except stem.OperationFailed as err:
        log.warning("Failed to attach stream because: %s" % err)

def new_event(event):
    print("New event")
    if isinstance(event, stem.response.events.CircuitEvent):
        new_circuit(event)
    elif isinstance(event, stem.response.events.StreamEvent):
        new_stream(event)
    else:
        log.warning("Received unexpected event %s." % str(event))

def resolve_exit():
    sock = torsocks.torsocket()
    sock.settimeout(10)

    for domain in list(domains.keys()):
        try:
            ipv4 = sock.resolve(domain)
            print("Yeah: ", ipv4)
        except error.SOCKSv5Error as err:
            print("Exit relay %s could not resolve IPv4 address for "
                          "\"%s\" because: %s" % (exit, domain, err))
            return False
        except socket.timeout as err:
            print(
                "Socket over exit relay %s timed out: %s" % (exit, err))
            return False
        except EOFError as err:
            print("EOF error: %s" % err)
            return False
        
        print(ipv4)

        if ipv4 not in domains[domain]:
            print("Exit relay %s returned unexpected IPv4 address %s "
                             "for domain %s" % (exit, ipv4, domain))
            return False
        else:
            print("IPv4 address of domain %s as expected for %s." %
                          (domain, exit))

    return True

def bootstrap():
    ports = {}
    # partial_parse_log_lines = functools.partial(parse_log_lines, ports)
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
        )
        log.info("Successfully started Tor process (PID=%d)." % proc.pid)
    except OSError as err:
        log.error("Couldn't launch Tor: %s.  Maybe try again?" % err)
        sys.exit(1)

    return ports["socks"], ports["control"]


if __name__ == "__main__":
    socks_port, control_port = bootstrap()
    controller = Controller.from_port(port=control_port)
    controller.authenticate(password="password") 
    controller.add_event_listener(print_bw, EventType.BW)
    setup()
    setup_task()
    controller.add_event_listener(new_event, EventType.CIRC, EventType.STREAM)
    update_finger_name_list()
    all_hops = get_finger_name_list()
    exit_hops = get_exits()
    for hop in exit_hops:
        try:
            all_hops.remove(hop)
        except:
            pass
    controller.new_circuit([all_hops[0], exit_hops[1]]) # For Debug
    # controller.new_circuit(["6B494FEAAE8010B68E05B77EBDDEADB2D9728E60", "7BA5141BCC216A6160E9D3B42111AB8599E99E48"])
    # resolve_exit("7BA5141BCC216A6160E9D3B42111AB8599E99E48")
    time.sleep(300)
