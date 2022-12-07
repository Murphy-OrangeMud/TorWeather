from .model import insert_fingerprint_spaces
from .config import url_helper
from .config import config


_SUBJECT_HEADER = '[Tor Weather]'
_SENDER = "Tor Weather <noreply@{}>".format(config.email_base_url)

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

_FINGERPRINT_NOT_FOUND_SUBJ = 'Fingerprint not found in stable relay list'
_FINGERPRINT_NOT_FOUND_MAIL = 'Hello, your fingerprint is not found in the stable relay list. '+\
    "Maybe you should run your relay a longer time to be recorded into the Tor fingerprint list. Welcome back again."

_WELCOME_SUBJ = 'Welcome to Tor!'
_WELCOME_MAIL = "Hello and welcome to Tor!\n\n" +\
    "This is a Tor Weather welcome email."+\
    "We've noticed that your Tor node %s has been running long "+\
    "enough to be "+\
    "flagged as \"stable\". First, we would like to thank you for your "+\
    "contribution to the Tor network! As Tor grows, we require ever more "+\
    "nodes to improve browsing speed and reliability for our users. "+\
    "Your node is helping to serve the millions of Tor clients out there."+\
    "%sThank you again for your contribution to the Tor network! "+\
    "We won't send you any further emails unless you subscribe.\n\n%s"

_LEGAL_INFO = "Additionally, since you are running as an exit node, you " +\
    "might be interested in Tor's Legal FAQ for Relay Operators "+\
    "(https://www.torproject.org/eff/tor-legal-faq.html.en) " +\
    "and Mike Perry's blog post on running an exit node " +\
    "(https://blog.torproject.org/blog/tips-running-exit-node-minimal-"+\
    "harassment).\n\n"

_GENERIC_FOOTER = "\n\nYou can unsubscribe from these reports at any time "+\
    "by posting request (Format: \{\"email\":\"YOUR_EMAIL\", \"fingerprint\":\"NODE_FINGERPRINT\"\}) to the following url:\n\n%s\n\nor change your Tor Weather "+\
    "notification preferences here by posting another request whose format is the same as subscribe: \n\n%s"


def _add_generic_footer(msg):
    unsubURL = url_helper.get_unsubscribe_url()
    prefURL = url_helper.get_preferences_url()
    footer = _GENERIC_FOOTER % (unsubURL, prefURL)
    
    return msg + footer

def _get_router_name(fingerprint, name):
    spaced_fingerprint = insert_fingerprint_spaces(fingerprint) 
    if name == 'Unnamed':
        return "(id: %s)" % spaced_fingerprint
    else:
        return "%s (id: %s)" % (name, spaced_fingerprint)

def bandwidth_tuple(recipient, fingerprint, name,  observed, threshold):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _LOW_BANDWIDTH_SUBJ
    sender = _SENDER

    msg = _LOW_BANDWIDTH_MAIL % (router, observed, threshold)
    msg = _add_generic_footer(msg)

    return (subj, msg, sender, [recipient])


def node_down_tuple(recipient, fingerprint, name, grace_pd):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _NODE_DOWN_SUBJ
    sender = _SENDER
    num_hours = str(grace_pd) + " hour"
    if grace_pd > 1:
        num_hours += "s"
    msg = _NODE_DOWN_MAIL % (router, num_hours)
    msg = _add_generic_footer(msg)
    return (subj, msg, sender, [recipient])


def version_tuple(recipient, fingerprint, name, version_type):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _VERSION_SUBJ
    sender = _SENDER
    version_type = version_type.lower()
    downloadURL = url_helper.get_download_url()
    msg = _VERSION_MAIL % (router, version_type, downloadURL)
    msg = _add_generic_footer(msg)
                           
    return (subj, msg, sender, [recipient])


def dns_tuple(recipient, fingerprint, name):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _DNS_FAIL_SUBJ
    sender = _SENDER
    msg = _DNS_FAIL_MAIL % router
    msg = _add_generic_footer(msg)
    return (subj, msg, sender, [recipient])


def not_found_tuple(recipient, fingerprint, name):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _FINGERPRINT_NOT_FOUND_SUBJ
    sender = _SENDER
    msg =_FINGERPRINT_NOT_FOUND_MAIL % router
    msg = _add_generic_footer(msg)
    return (subj, msg, sender, [recipient])


def welcome_tuple(recipient, fingerprint, name, exit):
    router = _get_router_name(fingerprint, name)
    subj = _SUBJECT_HEADER + _WELCOME_SUBJ
    sender = _SENDER
    append = ''
    # if the router is an exit node, append legal info 
    if exit:
        append = _LEGAL_INFO
    url = url_helper.get_home_url()
    msg = _WELCOME_MAIL % (router, url, append)
    return (subj, msg, sender, [recipient])

