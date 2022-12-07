import json
from flask import Flask
from config import config
from flask_mail import Mail, Message
import emails
import requests
from flask import jsonify

app = Flask(__name__)

@app.route('/', methods=('GET',))
def send_email():
    subject, text, sender, receipient = emails.welcome_tuple(config.email_username, "123", "Murphy", False)
    print(subject, text)
    print(config.email_api_key, config.email_base_url)
    
    requests.post("https://api.mailgun.net/v3/{}/messages".format(config.email_base_url),
                    auth=("api", config.email_api_key),
                    data={
                        "from": "Tor Weather <noreply@{}>".format(config.email_base_url),
                        "to": ["chengzhiyi2000@gmail.com"],
                        "subject": subject,
                        "text": text
                    })
    return jsonify({"Status": "OK"}), 200

if __name__ == '__main__':
    with app.app_context():
        app.run(debug=True)
