import os

path = os.path.split(os.path.realpath(__file__))[0]
authenticator = open(os.path.join(path, "auth_token"), "r").read().strip()

control_port = 9051
# TBD
base_url = "https://weather.dev"