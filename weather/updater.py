from datetime import datetime
from email.message import Message
import logging
from smtplib import SMTPException

from ctlutil import CtlUtil
from model import BandwithSub, DeployedDatetime, Subscriber, Router, NodeDownSub, OutdatedVersionSub, DNSFailSub, Session, hours_since
from config import config

from stem.control import EventType
import stem.descriptor
import stem

import emails
import random
import time

from flask import current_app
from flask_mail import Mail, Message

session = Session()


def get_fingerprints(cached_consensus_path, exclude=[]):
    fingerprints = []

    for desc in stem.descriptor.parse_file(cached_consensus_path):
        if desc.fingerprint not in exclude:
            fingerprints.append(desc.fingerprint)

    return fingerprints


def check_node_down(ctl_util, email_list):
    print("Checking node down...")
    subs = session.query(NodeDownSub).all()

    for sub in subs:
        if sub.router.subscriber.confirmed:
            print(sub.router, sub.router.subscriber.email)
            new_sub = sub
            if sub.router.up:
                if sub.triggered:
                    new_sub.triggered = False
                    new_sub.emailed = False
                    new_sub.last_changed = datetime.now()

            else:
                if not sub.triggered:
                    new_sub.triggered = True
                    new_sub.last_changed = datetime.now()

                if sub.triggered and (hours_since(sub.last_changed) >= sub.grace_pd) and sub.emailed == False:
                    recipient = sub.router.subscriber.email
                    fingerprint = sub.router.fingerprint
                    name = sub.router.name
                    grace_pd = sub.grace_pd

                    email = emails.node_down_tuple(recipient, fingerprint,
                                                    name, grace_pd)

                    email_list.append(email)
                    new_sub.emailed = True

            session.delete(sub)
            session.add(new_sub)
            session.commit()

    return email_list


def check_low_bandwith(ctl_util, email_list):
    print("Checking low bandwidth...")
    subs = session.query(BandwithSub).all()

    ctl_util.get_bandwidths()

    for sub in subs:
        fingerprint = str(sub.router.fingerprint)
        new_sub = sub

        if sub.router.subscriber.confirmed:
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
                    new_sub.emailed = True
            else:
                new_sub.emailed = False

            session.delete(sub)
            session.add(new_sub)
            session.commit()

    return email_list


def check_version(ctl_util, email_list):
    print("Checking version...")
    subs = session.query(OutdatedVersionSub).all()

    for sub in subs:
        if sub.router.subscriber.confirmed:
            fingerprint = str(sub.router.fingerprint)
            version_type = 'OBSOLETE'  # TODO: verify and add "get_version_type"
            new_sub = sub

            if version_type != 'ERROR':
                if version_type == 'OBSOLETE':
                    if sub.emailed == False:
                        fingerprint = sub.router.fingerprint
                        name = sub.router.name
                        recipient = sub.router.subscriber.email
                        email = emails.version_tuple(recipient,
                                                    fingerprint,
                                                    name,
                                                    version_type)

                        email_list.append(email)
                        new_sub.emailed = True

                else:
                    new_sub.emailed = False
            else:
                logging.info("Couldn't parse the version relay %s is running"
                              % str(sub.subscriber.router.fingerprint))

            session.delete(sub)
            session.add(new_sub)
            session.commit()

    return email_list


def check_dns_failure(ctl_util, email_list):
    print("Checking dns failure...")
    subs = session.query(DNSFailSub).all()
    random.shuffle(subs)

    ctl_util.control.add_event_listener(ctl_util.new_event, EventType.CIRC, EventType.STREAM)
    ctl_util.setup_task()

    fingerprints = ctl_util.get_finger_name_list()
    all_hops = list(fingerprints)

    for sub in subs:
        if not sub.router.exit:
            continue
        fingerprint = str(sub.router.fingerprint)

        if sub.router.subscriber.confirmed:
            try:
                all_hops.remove(fingerprint)
            except ValueError:
                pass

            first_hop = random.choice(all_hops)
            logging.debug("Using random first hop %s for circuit." % first_hop)
            hops = [first_hop, fingerprint]

            assert len(hops) > 1

            try:
                ctl_util.control.new_circuit(hops)
            except stem.ControllerError as err:
                recipient = sub.router.subscriber.email
                name = sub.router.name
                email = emails.dns_tuple(
                    recipient, fingerprint, name)
                email_list.append(email)

        time.sleep(3)

    fingerprint_list = ctl_util.queue_reader()
    for fpr in fingerprint_list:
        router = Router.query.filter_by(fingerprint=fpr).first()
        recipient = router.subscriber.email
        name = router.name
        email = emails.dns_tuple(
            recipient, fingerprint, name)
        email_list.append(email)


def check_all_subs(ctl_util, email_list):
    check_node_down(ctl_util, email_list)
    check_version(ctl_util, email_list)
    check_low_bandwith(ctl_util, email_list)
    check_dns_failure(ctl_util, email_list)


def update_all_routers(ctl_util, email_list):
    deployed_query = session.query(DeployedDatetime).all()
    if len(deployed_query) == 0:
        deployed = datetime.now()
        session.add(DeployedDatetime(deployed))
        session.commit()
    else:
        deployed = deployed_query[0].deployed

    if (datetime.now() - deployed).days < 2:
        fully_deployed = False
    else:
        fully_deployed = True

    router_set = session.query(Router).all()
    for router in router_set:
        if (datetime.now() - router.last_seen).days > 365:
            session.delete(router)
        else:
            new_router = router
            new_router.up = False
            session.delete(router)
            session.add(new_router)

        session.commit()

    finger_name = ctl_util.get_finger_name_list()

    for router in finger_name:
        finger = router[0]
        name = router[1]

        router_data = None
        try:
            router_data = session.query(Router).filter_all(fingerprint=finger).first()
            new_router_data = router_data
            session.delete(router_data)
            session.commit()
        except:
            if fully_deployed:
                router_data = Router(name=name, fingerprint=finger, welcomed=False)
            else:
                router_data = Router(name=name, fingerprint=finger, welcomed=True)

        new_router_data = router_data
        new_router_data.last_seen = datetime.now()
        new_router_data.name = name
        new_router_data.up = True
        new_router_data.exit = ctl_util.is_exit(finger)

        if router_data.welcomed == False and ctl_util.is_stable(finger):
            recipient = ctl_util.get_email(finger)
            is_exit = ctl_util.is_exit(finger)
            if not recipient == "":
                email = emails.welcome_tuple(recipient, finger, name, is_exit)
                email_list.append(email)

            new_router_data.welcomed = True
            new_router_data.exit = is_exit

        session.add(new_router_data)
        session.commit()

    return email_list


def run_all():
    ctl_util = CtlUtil()
    email_list = []
    email_list = update_all_routers(ctl_util, email_list)
    email_list = check_all_subs(ctl_util, email_list)

    current_app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    current_app.config['MAIL_PORT'] = 465
    current_app.config['MAIL_USERNAME'] = config.email_username
    current_app.config['MAIL_PASSWORD'] = config.email_password
    current_app.config['MAIL_USE_TLS'] = False
    current_app.config['MAIL_USE_SSL'] = True

    mail = Mail(current_app)

    with mail.connect() as conn:
        for email in email_list:
            subj, body, sender, recipients = email
            msg = Message(subj, 
                          body=body, 
                          sender=sender, 
                          recipients=recipients)

            conn.send(msg)
            
if __name__ == "__main__":
    run_all()

