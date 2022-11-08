from flask import Flask
from config import config
from flask_mail import Mail, Message


app = Flask(__name__)

@app.route('/', methods=('GET',))
def send_email():
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 465
    app.config['MAIL_USERNAME'] = config.email_username
    app.config['MAIL_PASSWORD'] = config.email_password
    app.config['MAIL_USE_TLS'] = False
    app.config['MAIL_USE_SSL'] = True

    mail = Mail(app)
    email_list = ["chengzhiyi2000@gmail.com"]

    with mail.connect() as conn:
        for email in email_list:
            subj, body, sender, recipients = email
            msg = Message(subj, 
                          body=body, 
                          sender=sender, 
                          recipients=recipients)

            conn.send(msg)

if __name__ == '__main__':
    with app.app_context():
        app.run(debug=True)
