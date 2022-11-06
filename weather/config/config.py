import os

path = os.path.split(os.path.realpath(__file__))[0]
authenticator = open(os.path.join(path, "auth_token"), "r").read().strip()

control_port = 9051
sql_alchemy_uri = "sqlite:////tmp/test.db"

# TBD
base_url = "https://127.0.0.1:5000"