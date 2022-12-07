import os

path = os.path.split(os.path.realpath(__file__))[0]
authenticator = open(os.path.join(path, "auth_token"), "r").read().strip()

sql_alchemy_uri = "sqlite:////tmp/test.db"

# TBD
base_url = "https://143.244.159.29/"

grace_pd = 48
threshold = 20

email_api_key = os.getenv("API_KEY")
email_base_url = os.getenv("API_BASE")
