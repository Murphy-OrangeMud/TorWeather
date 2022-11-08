from .config import base_url


_FINGERPRINT_NOT_FOUND = '/fingerprint_not_found/%s/'
_HOME = '/'
_PREFERENCES = '/update'
_SUBSCRIBE = '/subscribe/'
_UNSUBSCRIBE = '/unsubscribe/'
_DOWNLOAD = 'https://www.torproject.org/easy-download.html'

def get_fingerprint_info_ext(fingerprint):
    extension = _FINGERPRINT_NOT_FOUND % fingerprint
    return extension

def get_home_ext():
    extension = _HOME
    return extension

def get_home_url():
    url = base_url + _HOME
    return url

def get_preferences_url():
    url = base_url + _PREFERENCES
    return url

def get_preferences_ext():
    ext = _PREFERENCES
    return ext

def get_subscribe_ext():
    extension = _SUBSCRIBE
    return extension

def get_unsubscribe_url():
    url = base_url + _UNSUBSCRIBE
    return url

def get_download_url():
    return _DOWNLOAD
