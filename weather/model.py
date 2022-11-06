import base64
from datetime import datetime
import email
import re

from flask import current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine

from enum import Enum
import base64
import os
from config import config

engine = create_engine(config.sql_alchemy_uri)
db = SQLAlchemy()


def insert_fingerprint_spaces(fingerprint):
    return ' '.join(re.findall('.{4}', str(fingerprint)))

def get_rand_string():
    r = base64.urlsafe_b64encode(os.urandom(18))

    if r.endswith(bytes("-", encoding='utf-8')):
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
    last_seen = db.Column(db.DateTime)
    up = db.Column(db.Boolean)
    exit = db.Column(db.Boolean)

    subscriber_id = db.Column(db.String, db.ForeignKey('subscriber.email'))

    subscriptions = db.relationship('Subscription', backref='router', lazy=True)

    def __init__(self, fingerprint=None,
                       subscriber=None,
                       name='Unnamed',
                       welcomed=False,
                       last_seen=None,
                       up=True,
                       exit=False):
        super().__init__()
        self.fingerprint = fingerprint
        self.welcomed = welcomed
        self.name = name
        if last_seen is None:
            last_seen = datetime.now()
        self.last_seen = last_seen
        self.up = up
        self.exit = exit
        self.subscriber_id = subscriber

    def __repr__(self):
        return self.name + ": " + self._spaced_fingerprint()

    def _spaced_fingerprint(self):
        return insert_fingerprint_spaces(self.fingerprint)


class Subscriber(db.Model):
    email = db.Column(db.String, primary_key=True, unique=True)
    # router = db.Column(db.String, db.ForeignKey(Router.fingerprint), primary_key=True)
    confirmed = db.Column(db.Boolean)
    confirm_auth = db.Column(db.String)
    unsubs_auth = db.Column(db.String)
    pref_auth = db.Column(db.String)
    sub_date = db.Column(db.DateTime)

    routers = db.relationship('Router', backref='subscriber', lazy=True)

    def __init__(self, email=None,
                       confirmed=False,
                       confirm_auth=None,
                       unsubs_auth=None,
                       pref_auth=None):
        super().__init__()
        self.email = email
        self.confirmed = confirmed
        if confirm_auth is None:
            confirm_auth = get_rand_string()
        self.confirm_auth = confirm_auth
        if unsubs_auth is None:
            unsubs_auth = get_rand_string()
        self.unsubs_auth = unsubs_auth
        if pref_auth is None:
            pref_auth = get_rand_string()
        self.pref_auth = pref_auth
        self.sub_date = datetime.now()

    def __repr__(self):
        return self.email


class Subscription(db.Model):
    id = db.Column(db.String, primary_key=True, unique=True)
    # subscriber_id = db.Column(db.String, db.ForeignKey(Subscriber.email))
    router_id = db.Column(db.String, db.ForeignKey(Router.fingerprint))
    emailed = db.Column(db.Boolean)

    # subscriber_id = db.relationship('Subscriber', foreign_keys='Subscriber.email')
    # router_id = db.relationship('Router', foreign_keys='Rrouer.fingerprint')

    def __init__(self, router, emailed=False):
        super().__init__()
        self.id = get_rand_string()
        self.router_id = router
        self.emailed = emailed


class NodeDownSub(Subscription):
    triggered = db.Column(db.Boolean)
    grace_pd = db.Column(db.Integer)
    last_changed = db.Column(db.DateTime)

    def __init__(self, router, emailed=False, grace_pd=None, last_changed=None):
        super().__init__(router, emailed)
        self.grace_pd = grace_pd
        if last_changed is None:
            last_changed = datetime.now()
        self.last_changed = last_changed

    def is_graced_passed(self):
        if self.triggered and hours_since(self.last_changed) >= self.grace_pd:
            return True
        else:
            return False


class OutdatedVersionSub(Subscription):
    notify_type = db.Column(db.String)

    def __init__(self, router, emailed=False, notify_type='OBSOLETE'):
        super().__init__(router, emailed)
        self.notify_type = notify_type


class BandwithSub(Subscription):
    threshold = db.Column(db.Integer)

    def __init__(self, router, emailed=False, threshold=20):
        super().__init__(router, emailed)
        self.threshold = threshold


class DNSFailSub(Subscription):
    def __init__(self, router, emailed=False):
        super().__init__(router, emailed)


class DeployedDatetime(db.Model):
    
    deployed = db.Column(db.DateTime, primary_key=True)

    def __init__(self, deployed):
        super().__init__()
        self.deployed = deployed

    def __repr__(self):
        return self.deployed

