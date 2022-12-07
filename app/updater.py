from datetime import datetime
from email.message import Message
import logging
from smtplib import SMTPException
from typing import Set

from ctlutil import CtlUtil
from model import BandwithSub, Subscription,DeployedDatetime, Subscriber, Router, NodeDownSub, OutdatedVersionSub, DNSFailSub, Session, hours_since
from config import config

from stem.control import EventType
import stem.descriptor
import stem

from . import emails
import random
import time
import requests

from flask import current_app
from flask_mail import Mail, Message

log = logging.getLogger(__name__)

session = Session()

def check_node_down(ctl_util, email_list):
    log.debug("Checking node down...")
    subs = session.query(NodeDownSub).all()

    for sub in subs:
        if sub.router.up:
            if sub.triggered:
                sub.triggered = False
                sub.emailed = False
                sub.last_changed = datetime.now()

        else:
            if not sub.triggered:
                sub.triggered = True
                sub.last_changed = datetime.now()

            if sub.triggered and (hours_since(sub.last_changed) >= sub.grace_pd) and sub.emailed == False:
                recipient = sub.router.subscriber.email
                fingerprint = sub.router.fingerprint
                name = sub.router.name
                grace_pd = sub.grace_pd

                email = emails.node_down_tuple(recipient, fingerprint,
                                                name, grace_pd)

                email_list.append(email)
                sub.emailed = True

        session.commit()

    return email_list


def check_low_bandwith(ctl_util, email_list):
    log.debug("Checking low bandwidth...")
    subs = session.query(BandwithSub).all()

    ctl_util.get_bandwidths()

    for sub in subs:
        fingerprint = str(sub.router.fingerprint)

        bandwidth = ctl_util.get_bandwidth(fingerprint)
        if bandwidth < 0:
            continue
        if bandwidth < sub.threshold:
            if sub.emailed == False:
                recipient = sub.router.subscriber.email
                fingerprint = sub.router.fingerprint
                name = sub.router.name
                email = emails.bandwidth_tuple(recipient,
                                                    fingerprint, name, bandwidth, sub.threshold)

                email_list.append(email)
                sub.emailed = True
        else:
            sub.emailed = False

        session.commit()

    return email_list


def check_version(ctl_util, email_list):
    log.debug("Checking version...")
    subs = session.query(OutdatedVersionSub).all()

    for sub in subs:
        fingerprint = str(sub.router.fingerprint)
        version_type = 'OBSOLETE' 

        if version_type != 'ERROR':
            if version_type == 'OBSOLETE':
                if sub.emailed == False:
                    fingerprint = sub.router.fingerprint
                    name = sub.router.name
                    recipient = sub.router.subscriber_id
                    email = emails.version_tuple(recipient,
                                                fingerprint,
                                                name,
                                                version_type)

                    email_list.append(email)
                    sub.emailed = True

            else:
                sub.emailed = False
        else:
            log.info("Couldn't parse the version relay %s is running"
                            % str(sub.subscriber.router.fingerprint))
        session.commit()

    return email_list


def check_dns_failure(ctl_util, email_list):
    log.debug("Checking dns failure...")
    subs = session.query(DNSFailSub).all()
    random.shuffle(subs)

    ctl_util.control.add_event_listener(ctl_util.new_event, EventType.CIRC, EventType.STREAM)
    ctl_util.setup_task()

    all_hops, names = ctl_util.get_finger_name_list()

    for sub in subs:
        if not sub.router.exit:
            continue
        elif ctl_util.is_bad_exit(sub.router.fingerprint):
            recipient = sub.router.subscriber.email
            name = sub.router.name
            email = emails.dns_tuple(
                recipient, sub.router.fingerprint, name)
            email_list.append(email)
            continue

        ctl_util.total_circuits += 1

        fingerprint = str(sub.router.fingerprint)

        try:
            all_hops.remove(fingerprint)
        except ValueError:
            pass

        first_hop = random.choice(all_hops)
        log.debug("Using random first hop %s for circuit." % first_hop)
        hops = [first_hop, fingerprint]

        assert len(hops) > 1

        try:
            log.debug("Trying to build new cirtuit for %s" % fingerprint)
            ctl_util.control.new_circuit(hops)
        except stem.ControllerError as err:
            ctl_util.failed_circuits += 1
            log.debug("Circuit with exit relay \"%s\" could not be "
                      "created: %s" % (fingerprint, err))
            recipient = sub.router.subscriber.email
            name = sub.router.name
            email = emails.dns_tuple(
                recipient, fingerprint, name)
            email_list.append(email)

        time.sleep(3)

    fingerprint_list = ctl_util.finished()
    for fpr in fingerprint_list:
        router = session.query(Router).filter_by(fingerprint=fpr).first()
        recipient = router.subscriber.email
        name = router.name
        email = emails.dns_tuple(
            recipient, fingerprint, name)
        email_list.append(email)

    return email_list


def check_all_subs(ctl_util, email_list):
    email_list = check_node_down(ctl_util, email_list)
    email_list = check_version(ctl_util, email_list)
    email_list = check_low_bandwith(ctl_util, email_list)
    log.debug("Now we have %d emails" % len(email_list))
    email_list = check_dns_failure(ctl_util, email_list)
    log.debug("Now we have %d emails" % len(email_list))
    return email_list


def update_all_routers(ctl_util, email_list):
    finger_list, name_list = ctl_util.get_finger_name_list()
    router_set = session.query(Router).all()
    for router in router_set:
        if (datetime.now() - router.last_seen).days > 365:
            session.delete(router)
        else:
            router.up = False
            if router.fingerprint in finger_list:
                router.up = True
                router.exit = ctl_util.is_exit(router.fingerprint)
                router.last_seen = datetime.now()
                if router.welcomed == False:
                    recipient = router.subscriber_id
                    is_exit = router.exit
                    if not recipient == "":
                        email = emails.welcome_tuple(recipient, router.fingerprint, router.name, is_exit)
                        email_list.append(email)
                    router.welcomed = True

            session.commit()

        # session.commit()

    log.debug("Finished updating routers, discovering %d vulnerabilities" % len(email_list))

    return email_list


def run_all():
    logging.getLogger("stem").setLevel(logging.__dict__["DEBUG"])
    log_format = "%(asctime)s %(name)s [%(levelname)s] %(message)s"
    logging.basicConfig(format=log_format,
                        level=logging.__dict__["DEBUG"],
                        filename=None)
    ctl_util = CtlUtil()
    email_list = []
    email_list = update_all_routers(ctl_util, email_list)
    email_list = check_all_subs(ctl_util, email_list)

    for email in email_list:
        subj, body, sender, recipients = email
        print(sender, recipients)
        resp = requests.post("https://api.mailgun.net/v3/{}/messages".format(config.email_base_url),
                        auth=("api", config.email_api_key),
                        data={
                        "from": sender,
                        "to": recipients,
                        "subject": subj,
                        "text": body
                    })
        print(resp.content)

            
if __name__ == "__main__":
    run_all()

