from flask import Flask
from flask import request
from flask import jsonify
from http.client import HTTPException, HTTPResponse
from model import BandwithSub, DNSFailSub, NodeDownSub, OutdatedVersionSub, Subscriber, Router, Session, Base, init_db
from config import url_helper
from config import config

app = Flask(__name__)
session = Session()

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

        subscriber = session.query(Subscriber).filter_by(email=email).all()
        if len(subscriber) == 0:
            subscriber = Subscriber(email=email)
            session.add(subscriber)
            session.commit()
        else:
            subscriber = subscriber[0]

        routers = session.query(Router).filter_by(fingerprint=fingerprint).all()
        if len(routers) > 0:
            router = routers[0]
            return jsonify({"status": "Error", "msg": 'already_subscribed'}), 401

        router = Router(fingerprint=fingerprint, subscriber=email)
        session.add(router)
        session.commit()

        if get_node_down_sub:
            try:
                grace_pd = json["node_down_grace_pd"]
            except:
                grace_pd = config.grace_pd
            node_down_sub = NodeDownSub(router=fingerprint, grace_pd=grace_pd)
            session.add(node_down_sub)
            session.commit()

        if get_version:
            version_sub = OutdatedVersionSub(router=fingerprint)
            session.add(version_sub)
            session.commit()

        if get_low_bandwidth:
            try:
                band_low_threshold = eval(json['band_low_threshold'])
            except:
                band_low_threshold = 20
            band_low_sub = BandwithSub(
                router=fingerprint, threshold=band_low_threshold)
            session.add(band_low_sub)
            session.commit()

        if get_dns_fail:
            dns_sub = DNSFailSub()
            session.add(dns_sub)
            session.commit()

        return jsonify({"status": "OK"}), 200

@app.route('/unsubscribe', methods=('POST',))
def unsubscribe():
    if request.method == 'POST':
        json = request.get_json()

        try:
            email = json["email"]
            fingerprint = json["fingerprint"]
        except KeyError:
            return jsonify({"status": "Error", "msg": "Must provide email and fingerprint"}), 401

        try:
            unsub_node_down = eval(json["unsub_node_down"])
        except KeyError:
            unsub_node_down = False

        try:
            unsub_version = eval(json["unsub_version"])
        except KeyError:
            unsub_version = False
        
        try:
            unsub_low_bandwidth = eval(json["unsub_band_low"])
        except:
            unsub_low_bandwidth = False

        try:
            unsub_dns_fail = eval(json["unsub_dns_fail"])
        except:
            unsub_dns_fail = False

        if unsub_node_down:
            sub = session.query(NodeDownSub).filter_by(router=fingerprint).all()
            if len(sub) == 0:
                return jsonify({"status": "Error", "msg": "No node down subscription found"}), 401
            else:
                session.delete(sub[0])
                session.commit()
        
        if unsub_version:
            sub = session.query(OutdatedVersionSub).filter_by(router=fingerprint).all()
            if len(sub) == 0:
                return jsonify({"status": "Error", "msg": "No outdated version subscription found"}), 401
            else:
                session.delete(sub[0])
                session.commit()
        
        if unsub_low_bandwidth:
            sub = session.query(BandwithSub).filter_by(router=fingerprint).all()
            if len(sub) == 0:
                return jsonify({"status": "Error", "msg": "No low bandwidth subscription found"}), 401
            else:
                session.delete(sub[0])
                session.commit()

        if unsub_dns_fail:
            sub = session.query(DNSFailSub).filter_by(router=fingerprint).all()
            if len(sub) == 0:
                return jsonify({"status": "Error", "msg": "No dns failure subscription found"}), 401
            else:
                session.delete(sub[0])
                session.commit()

        return jsonify({"status": "OK"}), 200

@app.route('/update', methods=('POST',))
def update():
    if request.method == 'POST':
        json = request.get_json()

        try:
            email = json["email"]
            fingerprint = json["fingerprint"]
            routers = session.query(Router).filter_by(fingerprint=fingerprint)
            if len(routers) == 0 or routers[0].subscriber_id != email:
                return jsonify({"status": "Error", "msg": "No subscription found, please subscribe first"}), 401
        except KeyError:
            return jsonify({"status": "Error", "msg": "Must provide email and fingerprint"}), 401

        try:
            get_node_down_sub = eval(json["get_node_down"])
            if get_node_down_sub:
                if "grace_pd" not in json:
                    grace_pd = config.grace_pd
                else:
                    grace_pd = eval(json["grace_pd"])
                sub = session.query(NodeDownSub).filter_by(router=fingerprint).all()
                if len(sub) == 0:
                    sub = NodeDownSub(router=fingerprint, grace_pd=grace_pd)
                    session.add(sub)
                    session.commit()
                else:
                    new_sub = sub
                    new_sub.grace_pd = grace_pd
                    session.delete(sub)
                    session.add(new_sub)
                    session.commit()
            else:
                sub = session.query(NodeDownSub).filter_by(router=fingerprint).all()
                if len(sub) > 0:
                    sub = sub[0]
                    session.delete(sub)
                    session.commit()
        except KeyError:
            pass

        try:
            get_version = eval(json["get_version"])
            if get_version:
                sub = session.query(OutdatedVersionSub).filter_by(router=fingerprint).all()
                if len(sub) == 0:
                    sub = OutdatedVersionSub(router=fingerprint)
                    session.add(sub)
                    session.commit()
            else:
                sub = session.query(OutdatedVersionSub).filter_by(router=fingerprint).all()
                if len(sub) > 0:
                    sub = sub[0]
                    session.delete(sub)
                    session.commit()
        except KeyError:
            pass

        try:
            get_low_bandwidth = eval(json["get_band_low"])
            if "" not in json:
                band_low_threshold = 20
            else:
                band_low_threshold = eval(json["band_low_threshold"])
            if get_low_bandwidth:
                sub = BandwithSub.query.filter_by(router=fingerprint).all()
                if len(sub) == 0:
                    sub = BandwithSub(router=fingerprint, threshold=band_low_threshold)
                    session.add(sub)
                    session.commit()
                else:
                    new_sub = sub
                    new_sub.threshold = band_low_threshold
                    session.delete(sub)
                    session.add(new_sub)
                    session.commit()
            else:
                sub = session.query(BandwithSub).filter_by(router=fingerprint).all()
                if len(sub) > 0:
                    sub = sub[0]
                    session.delete(sub)
                    session.commit()
        except:
            pass

        try:
            get_dns_fail = eval(json["get_dns_fail"])
            if get_dns_fail:
                sub = session.query(DNSFailSub).filter_by(router=fingerprint).all()
                if len(sub) == 0:
                    sub = DNSFailSub(router=fingerprint)
                    session.add(sub)
                    session.commit()
            else:
                sub = session.query(DNSFailSub).filter_by(router=fingerprint).all()
                if len(sub) > 0:
                    sub = sub[0]
                    session.delete(sub)
                    session.commit()
        except:
            pass

        return jsonify({"status": "OK"}), 200


if __name__ == "__main__":
    init_db()

    with app.app_context():
        app.run(debug=True)
        
    # session.close()

