# Tor Weather

This is a rewrite version of tor weather which support subscribing, unsubscribing and updating preferences by API.

Supporting preferences include informing subscribers by email when their nodes have a low bandwidth, fail to resolve DNS, are down, have an outdated version of Tor or lose the stable/guard/exit flag.

There should only be one running instance of the website. 

### How to run locally

**OPTIONAL**
```
pip install virtualenv
virtualenv venv
source venv/bin/activate
```

**THE WEBSITE**
```
pip install -r requirements
python weather/api.py
```

**THE CRONJOB**
```
python /ABSOLUTE/PATH/TO/THE/APP/weather/updater.py
```

### Tests
```
python weather/test_dns.py
python weather/test_email.py
```

### TODO
[ ] Add functions

    [ ] Email users when their relay are affected by a security vulnerability

    [ ] Email users when their MyFamily configuration is broken

    [ ] Email users when there are suggestions for configuration improvements for their relay

    [ ] Email users when their relays are on the top 20/50/100 relays list

    [ ] Email users when they get a T-shirt

    [ ] Email users about new relay requirements

[ ] Add auth and confirm mechanism
