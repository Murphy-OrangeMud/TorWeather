import os

path = os.path.split(os.path.realpath(__file__))[0]
authenticator = open(os.path.join(path, "auth_token"), "r").read().strip()

control_port = 9051
sql_alchemy_uri = "sqlite:////tmp/test.db"

# TBD
base_url = "https://127.0.0.1:5000"

email_username = 'usedforatlasmurphy@gmail.com'
email_password = 'gobluejays2022'

grace_pd = 48
threshold = 20

email_api_key = open(os.path.join(path, "api_key"), "r").read().strip()
email_base_url = open(os.path.join(path, "api_base"), "r").read().strip()
