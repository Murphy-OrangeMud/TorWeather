import base64
from datetime import datetime
import email
import re

from flask import current_app
from flask_sqlalchemy import SQLAlchemy

from enum import Enum
import base64
import os

from sqlalchemy import ForeignKey

db = SQLAlchemy(current_app)


def insert_fingerprint_spaces(fingerprint):
    return ' '.join(re.findall('.{4}', str(fingerprint)))

def get_rand_string():
    r = base64.urlsafe_b64decode(os.urandom(18))

    if r.endswith("-"):
        r = r.replace("-", "x")
    return r

def hours_since(time):
    delta = datetime.now() - time
    hours = (delta.days * 24) + (delta.seconds / 3600)
    return hours


class Router(db.Model):
    fingerprint = db.Column(db.String, primary_key=True, unique=True)
    name = db.Column(db.String)
    welcomed = db.Column(db.Boolean)
    last_seen = db.Column(db.Datetime)
    up = db.Column(db.Boolean)
    exit = db.Column(db.Boolean)

    def __init__(self, fingerprint=None,
                       name='Unnamed',
                       welcomed=False,
                       last_seen=datetime.now,
                       up=True,
                       exit=False):
        super().__init__()
        self.fingerprint = fingerprint
        self.welcomed = welcomed
        self.name = name
        self.last_seen = last_seen
        self.up = up
        self.exit = exit

    def __repr__(self):
        return self.name + ": " + self._spaced_fingerprint()

    def _spaced_fingerprint(self):
        return insert_fingerprint_spaces(self.fingerprint)


class Subscriber(db.Model):
    email = db.Column(db.String, primary_key=True, unique=True)
    router = db.Column(db.String, db.ForeignKey(Router.fingerprint), primary_key=True)
    confirmed = db.Column(db.Boolean)
    confirm_auth = db.Column(db.String)
    unsubs_auth = db.Column(db.String)
    pref_auth = db.Column(db.String)
    sub_date = db.Column(db.DateTime)

    router = db.relationship('Router', foreign_keys='Router.fingerprint')

    def __init__(self, email=None,
                       router=None,
                       confirmed=False,
                       confirm_auth=get_rand_string,
                       unsubs_auth=get_rand_string,
                       pref_auth=get_rand_string,
                       sub_date=datetime.now):
        super().__init__()
        self.email = email
        self.router = router
        self.confirmed = confirmed
        self.confirm_auth = confirm_auth
        self.unsubs_auth = unsubs_auth
        self.pref_auth = pref_auth
        self.sub_date = sub_date

    def __repr__(self):
        return self.email


class Subscription(db.Model):
    subscriber = db.Column(db.String, db.ForeignKey(Subscriber.email), primary_key=True)
    emailed = db.Column(db.Boolean)

    subscriber = db.relationship('Subscriber', foreign_keys='Subscriber.email')

    def __init__(self, subscriber, emailed=False):
        super().__init__()
        self.subscriber = subscriber
        self.emailed = emailed


class NodeDownSub(Subscription):
    triggered = db.Column(db.Boolean)
    grace_pd = db.Column(db.Integer)
    last_changed = db.Column(db.DateTime)

    def __init__(self, subscriber, emailed=False, grace_pd=None, last_changed=datetime.now):
        super().__init__(subscriber, emailed)

    def is_graced_passed(self):
        if self.triggered and hours_since(self.last_changed) >= self.grace_pd:
            return True
        else:
            return False


class OutdatedVersionSub(Subscription):
    notify_type = db.Column(db.String, blank=False)

    def __init__(self, subscriber, emailed=False, notify_type='OBSOLETE'):
        super().__init__(subscriber, emailed)
        self.notify_type = notify_type


class BandwithSub(Subscription):
    threshold = db.Column(db.Integer, blank=False)

    def __init__(self, threshold=20):
        self.threshold = threshold


class DNSFailSub(Subscription):
    triggered = db.Column(db.Boolean)
    grace_pd = db.Column(db.Integer)
    last_changed = db.Column(db.DateTime)

    def __init__(self, subscriber, emailed=False, grace_pd=None, last_changed=datetime.now):
        super().__init__(subscriber, emailed)

    def is_graced_passed(self):
        if self.triggered and hours_since(self.last_changed) >= self.grace_pd:
            return True
        else:
            return False


class DeployedDatetime(db.Model):
    
    deployed = db.Column(db.DateTime)

    def __init__(self, deployed):
        super().__init__()
        self.deployed = deployed

    def __repr__(self):
        return self.deployed

