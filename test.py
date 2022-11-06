
import time
from stem.control import Controller, EventType
import weather.torsocks as torsocks
import weather.error as error
import logging
import dns.resolver
import socket


domains = {
    "www.youporn.com": [],
    "youporn.com": [],
    "www.torproject.org": [],
    "www.i2p2.de": [],
    "torrentfreak.com": [],
    "blockchain.info": [],
}


def setup():
    for domain in list(domains.keys()):
        response = dns.resolver.resolve(domain)
        for record in response:
            logging.debug("Domain %s maps to %s." % (domain, record.address))
            domains[domain].append(record.address)


def print_bw(event):
    print("Send: %i, Receive: %i" % (event.written, event.read))


def resolve_exit(fingerprint):
    sock = torsocks.torsocket()
    sock.settimeout(10)

    for domain in list(domains.keys()):
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

        if ipv4 not in domains[domain]:
            logging.critical("Exit relay %s returned unexpected IPv4 address %s "
                             "for domain %s" % (exit, ipv4, domain))
            return False
        else:
            logging.debug("IPv4 address of domain %s as expected for %s." %
                          (domain, exit))

    return True


with Controller.from_port(port=9051) as controller:
    controller.authenticate(password="password")
    controller.add_event_listener(print_bw, EventType.BW)
    setup()
    resolve_exit("7BA5141BCC216A6160E9D3B42111AB8599E99E48")
    time.sleep(300)
