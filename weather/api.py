from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import request
from flask import jsonify
from http.client import HTTPException
from config import url_helper
from config import config

import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = config.sql_alchemy_uri

@app.route('/subscribe', methods=('POST',))
def subscribe():
    if request.method == 'POST':
        json = request.get_json()

        email = json["email"]
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

        try:
            get_node_down_sub = eval(json["get_node_down"])
        except KeyError:
            get_node_down_sub = False

        try:
            if get_node_down_sub:
                node_down_sub = NodeDownSub(subscriber=subscriber, grace_pd=json["node_down_grace_pd"])
                db.session.add(node_down_sub)
                db.session.commit()
        except KeyError:
            return HTTPException("Wrong format, must provide node_down_grace_pd")

        try:
            if eval(json["get_version"]):
                version_sub = OutdatedVersionSub(subscriber=subscriber)
                db.session.add(version_sub)
                db.session.commit()
        except KeyError:
            pass

        try:
            get_low_bandwidth = eval(json["get_band_low"])
        except:
            get_low_bandwidth = False

        try:
            if get_low_bandwidth:
                band_low_sub = BandwithSub(subscriber=subscriber, threshold=json["band_low_threshold"])
                db.session.add(band_low_sub)
                db.session.commit()
        except KeyError:
            return HTTPException("Wrong format, must provide band_low_threshold")

        try:
            if eval(json["get_dns_fail"]):
                dns_sub = DNSFailSub()
                db.session.add(dns_sub)
                db.session.commit()
        except KeyError:
            pass

if __name__ == "__main__":
    with app.app_context():
        from model import BandwithSub, DNSFailSub, NodeDownSub, OutdatedVersionSub, Subscriber, db, Router
        db.init_app(app)
        db.create_all()
        app.run(debug=True)