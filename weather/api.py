from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import render_template
from flask import request
from flask import jsonify
from model import BandwithSub, DNSFailSub, NodeDownSub, OutdatedVersionSub, Subscriber, db, Router

from config import url_helper

import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = ""

@app.route('/subscribe', methods=('POST',))
def subscribe():
    if request.method == 'POST':
        json = request.get_json()

        email = json["email_1"]
        fingerprint = json["fingerprint"]
        router = Router.query.filter_by(fingerprint=fingerprint).all()

        subscriber = Subscriber.query.filter_by(email=email, fingerprint=fingerprint).all()
        if len(subscriber) > 0:
            subscriber = subscriber[0]
            url_extension = url_helper.get_error_ext('already_subscribed', 
                                               subscriber.pref_auth)
            raise Exception(url_extension)
        else:
            subscriber = Subscriber(email=email, fingerprint=fingerprint)
            db.session.add(subscriber)
            db.session.commit()

        if json["get_node_down"]:
            node_down_sub = NodeDownSub(subscriber=subscriber, grace_pd=json["node_down_grace_pd"])
            db.session.add(node_down_sub)
            db.session.commit()
        if json["get_version"]:
            version_sub = OutdatedVersionSub(subscriber=subscriber)
            db.session.add(version_sub)
            db.session.commit()
        if json["get_band_low"]:
            band_low_sub = BandwithSub(subscriber=subscriber, threshold=json["band_low_threshold"])
            db.session.add(band_low_sub)
            db.session.commit()
        if json["get_dns_fail"]:
            dns_sub = DNSFailSub()
            db.session.add(dns_sub)
            db.session.commit()




if __name__ == "__main__":
    with app.app_context():
        app.run(debug=True)