from model import insert_fingerprint_spaces
from config import url_helper


_SUBJECT_HEADER = '[Tor Weather]'
_SENDER = 'tor-ops@torproject.org'

_LOW_BANDWIDTH_SUBJ = 'Low bandwidth!'
_LOW_BANDWIDTH_MAIL = "This is a Tor Weather Report.\n\n"+\
    "It appears that the tor node %s you've been observing "+\
    "has an observed bandwidth capacity of %s kB/s. You elected to receive "+\
    "notifications if this node's bandwidth capacity passed a threshold of "+\
    "%s kB/s. You may wish to look at your router to see why."

_NODE_DOWN_SUBJ = 'Node Down!'
_NODE_DOWN_MAIL = "This is a Tor Weather Report.\n\n" +\
    "It appears that the node %s you've been observing " +\
    "has been uncontactable through the Tor network for at least %s. "+\
    "You may wish to look at it to see why."

_VERSION_SUBJ = 'Node Out of Date!'
_VERSION_MAIL = "This is a Tor Weather Report.\n\n"+\
    "It appears that the Tor node %s you've been observing "+\
    "is running an %s version of Tor. You can download the "+\
    "latest version of Tor at %s."

_DNS_FAIL_SUBJ = 'Failed to Resolve Hostnames!'
_DNS_FAIL_MAIL = "This is a Tor Weather Report.\n\n"+\
    "It appears that the node %s you've been observing " +\
    "has been failing to resolve hostnames and has DNS poisoned." +\
    "You may wish to look at it and fix."

_GENERIC_FOOTER = "\n\nYou can unsubscribe from these reports at any time "+\
    "by visiting the following url:\n\n%s\n\nor change your Tor Weather "+\
    "notification preferences here: \n\n%s"


def _add_generic_footer(msg, unsubs_auth, pref_auth):
    unsubURL = url_helper.get_unsubscribe_url(unsubs_auth)
    prefURL = url_helper.get_preferences_url(pref_auth)
    footer = _GENERIC_FOOTER % (unsubURL, prefURL)
    
    return msg + footer

def _get_router_name(fingerprint, name):
    spaced_fingerprint = insert_fingerprint_spaces(fingerprint) 
    if name == 'Unnamed':
        return "(id: %s)" % spaced_fingerprint
    else:
        return "%s (id: %s)" % (name, spaced_fingerprint)

def bandwidth_tuple(recipient, fingerprint, name,  observed, threshold, unsubs_auth, pref_auth):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _LOW_BANDWIDTH_SUBJ
    sender = _SENDER

    msg = _LOW_BANDWIDTH_MAIL % (router, observed, threshold)
    msg = _add_generic_footer(msg, unsubs_auth, pref_auth)

    return (subj, msg, sender, [recipient])


def node_down_tuple(recipient, fingerprint, name, grace_pd, unsubs_auth, pref_auth):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _NODE_DOWN_SUBJ
    sender = _SENDER
    num_hours = str(grace_pd) + " hour"
    if grace_pd > 1:
        num_hours += "s"
    msg = _NODE_DOWN_MAIL % (router, num_hours)
    msg = _add_generic_footer(msg, unsubs_auth, pref_auth)
    return (subj, msg, sender, [recipient])


def version_tuple(recipient, fingerprint, name, version_type, unsubs_auth, pref_auth):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _VERSION_SUBJ
    sender = _SENDER
    version_type = version_type.lower()
    downloadURL = url_helper.get_download_url()
    msg = _VERSION_MAIL % (router, version_type, downloadURL)
    msg = _add_generic_footer(msg, unsubs_auth, pref_auth)
                           
    return (subj, msg, sender, [recipient])


def dns_tuple(recipient, fingerprint, name, unsubs_auth, pref_auth):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _DNS_FAIL_SUBJ
    sender = _SENDER
    msg = _DNS_FAIL_MAIL % router
    msg = _add_generic_footer(msg, unsubs_auth, pref_auth)
    return (subj, msg, sender, [recipient])

