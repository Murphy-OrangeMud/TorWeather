from .config import base_url

_CONFIRM = '/confirm/%s/'
_CONFIRM_PREF = '/confirm_pref/%s/'
_ERROR = '/error/%s/%s/'
_FINGERPRINT_NOT_FOUND = '/fingerprint_not_found/%s/'
_HOME = '/'
_PENDING = '/pending/%s/'
_PREFERENCES = '/preferences/%s/'
_RESEND_CONF = '/resend_conf/%s/'
_SUBSCRIBE = '/subscribe/'
_UNSUBSCRIBE = '/unsubscribe/%s/'
_DOWNLOAD = 'https://www.torproject.org/easy-download.html'

def get_confirm_url(confirm_auth):
    url = base_url + _CONFIRM % confirm_auth
    return url

def get_confirm_pref_ext(pref_auth):
    extension = _CONFIRM_PREF % pref_auth
    return extension

def get_error_ext(error_type, key):
    extension = _ERROR % (error_type, key)
    return extension 

def get_fingerprint_info_ext(fingerprint):
    extension = _FINGERPRINT_NOT_FOUND % fingerprint
    return extension

def get_home_ext():
    extension = _HOME
    return extension

def get_home_url():
    url = base_url + _HOME
    return url

def get_pending_ext(confirm_auth):
    extension = _PENDING % confirm_auth
    return extension

def get_preferences_url(pref_auth):
    url = base_url + _PREFERENCES % pref_auth
    return url

def get_preferences_ext(pref_auth):
    ext = _PREFERENCES % pref_auth
    return ext

def get_resend_ext(confirm_auth):
    extension = _RESEND_CONF % confirm_auth
    return extension

def get_subscribe_ext():
    extension = _SUBSCRIBE
    return extension

def get_unsubscribe_url(unsubs_auth):
    url = base_url + _UNSUBSCRIBE % unsubs_auth
    return url

def get_download_url():
    return _DOWNLOAD
