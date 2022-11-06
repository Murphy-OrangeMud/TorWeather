from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import request
from flask import jsonify
from http.client import HTTPException, HTTPResponse
from config import url_helper
from config import config

import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = config.sql_alchemy_uri

@app.route('/subscribe', methods=('POST',))
def subscribe():
    if request.method == 'POST':
        json = request.get_json()

        try:
            email = json["email"]
            fingerprint = json["fingerprint"]
        except KeyError:
            return jsonify({"status": "Error", "msg": "Must provide email and fingerprint"}), 401

        try:
            get_node_down_sub = eval(json["get_node_down"])
        except KeyError:
            get_node_down_sub = False

        try:
            get_version = eval(json["get_version"])
        except KeyError:
            get_version = False
        
        try:
            get_low_bandwidth = eval(json["get_band_low"])
        except:
            get_low_bandwidth = False

        try:
            get_dns_fail = eval(json["get_dns_fail"])
        except:
            get_dns_fail = False

        if not (get_node_down_sub or get_version or get_low_bandwidth or get_dns_fail):
            return jsonify({"status": "Error", "msg": "Must have at least a subscription"}), 401

        subscriber = Subscriber.query.filter_by(email=email).all()
        if len(subscriber) == 0:
            subscriber = Subscriber(email=email)
            db.session.add(subscriber)
            db.session.commit()
        else:
            subscriber = subscriber[0]

        routers = Router.query.filter_by(fingerprint=fingerprint).all()
        if len(routers) > 0:
            router = routers[0]
            url_extension = url_helper.get_error_ext('already_subscribed', subscriber.pref_auth)
            return jsonify({"status": "Error", "msg": url_extension}), 401
        
        router = Router(fingerprint=fingerprint, subscriber=email)
        db.session.add(router)
        db.session.commit()

        if get_node_down_sub:
            try:
                grace_pd = json["node_down_grace_pd"]
            except:
                grace_pd = None
            node_down_sub = NodeDownSub(router=fingerprint, grace_pd=grace_pd)
            db.session.add(node_down_sub)
            db.session.commit()

        if get_version:
            version_sub = OutdatedVersionSub(router=fingerprint)
            db.session.add(version_sub)
            db.session.commit()

        if get_low_bandwidth:
            try:
                band_low_threshold = eval(json['band_low_threshold'])
            except:
                band_low_threshold = 20
            band_low_sub = BandwithSub(router=fingerprint, threshold=band_low_threshold)
            db.session.add(band_low_sub)
            db.session.commit()

        if get_dns_fail:
            dns_sub = DNSFailSub()
            db.session.add(dns_sub)
            db.session.commit()

        return jsonify({"status": "OK"}), 200

#TODO: Unsubscribe and update subscription

if __name__ == "__main__":
    with app.app_context():
        from model import BandwithSub, DNSFailSub, NodeDownSub, OutdatedVersionSub, Subscriber, db, Router
        try:
            db.drop_all()
        except:
            pass
        db.init_app(app)
        db.create_all()
        app.run(debug=True)

