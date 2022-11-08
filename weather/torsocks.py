import os
import struct
import socket
import select
import errno
import logging
import _socket
import socks
import error

proxy_addr = None
proxy_port = None
queue = None
circ_id = None

_orig_getaddrinfo = socket.getaddrinfo
orig_socket = socket.socket

_ERRNO_RETRY = frozenset((errno.EAGAIN, errno.EWOULDBLOCK,
                          errno.EINPROGRESS, errno.EINTR))

_LOCAL_SOCKETS = frozenset(
    getattr(socket, af) for af in [
        'AF_UNIX', 'AF_LOCAL',
        'AF_ROUTE', 'AF_KEY', 'AF_ALG', 'AF_NETLINK'
    ]
    if hasattr(socket, af)
)


# Map server-side SOCKSv5 errors to errno codes (as best we can; codes
# 1 and 7 don't correspond to documented error codes for connect(2))
socks5_errors = {
    0x00: 0,                   # Success
    0x01: errno.EIO,           # General failure
    0x02: errno.EACCES,        # Connection not allowed by ruleset
    0x03: errno.ENETUNREACH,   # Network unreachable
    0x04: errno.EHOSTUNREACH,  # Host unreachable
    0x05: errno.ECONNREFUSED,  # Connection refused by destination host
    0x06: errno.ETIMEDOUT,     # TTL expired
    0x07: errno.ENOTSUP,       # Command not supported / protocol error
    0x08: errno.EAFNOSUPPORT,  # Address type not supported
}

def send_queue(sock_name):
    global queue, circ_id
    assert (queue is not None) and (circ_id is not None)
    queue.put([circ_id, sock_name])

class _Torsocket(socks.socksocket):
    def __init__(self, *args, **kwargs):
        super(_Torsocket, self).__init__(*args, **kwargs)
        orig_neg = self._proxy_negotiators[2]
        def ourneg(*args, **kwargs):
            try:
               send_queue(args[0].getsockname())
               orig_neg(*args, **kwargs)
            except Exception as e:
                logging.debug("Error in custom negotiation function: {}".format(e))
        self._proxy_negotiators[2] = ourneg
    
    def negotiate(self):
        proxy_type, addr, port, rdns, username, password = self.proxy
        logging.warn((addr, port))
        socks._BaseSocket.connect(self, (addr, port))
        socks._BaseSocket.sendall(self, struct.pack('BBB', 0x05, 0x01, 0x00))
        socks._BaseSocket.recv(self, 2)

    def resolve(self, hostname):
        host = hostname.encode('utf-8')
        # First connect to the local proxy
        self.negotiate()
        print("Negotiate succeed")
        send_queue(socks._BaseSocket.getsockname(self))
        req = struct.pack('BBB', 0x05, 0xF0, 0x00)
        req += chr(0x03).encode() + chr(len(host)).encode() + host
        req = req + struct.pack(">H", 8444)
        socks._BaseSocket.sendall(self, req)
        # Get the response
        print("Get response")
        ip = ""
        resp = socks._BaseSocket.recv(self, 4)
        if resp[0:1] != chr(0x05).encode():
            socks._BaseSocket.close(self)
            raise error.SOCKSv5Error("SOCKS Server error")
        elif resp[1:2] != chr(0x00).encode():
            # Connection failed
            print("Connection failed")
            socks._BaseSocket.close(self)
            if ord(resp[1:2])<=8:
                raise error.SOCKSv5Error("SOCKS Server error {}".format(ord(resp[1:2])))
            else:
                raise error.SOCKSv5Error("SOCKS Server error 9")
        elif resp[3:4] == chr(0x01).encode():
            ip = socket.inet_ntoa(socks._BaseSocket.recv(self, 4))
        elif resp[3:4] == chr(0x03).encode():
            resp = resp + socks._BaseSocket.recv(self, 1)
            ip = socks._BaseSocket.recv(self, ord(resp[4:5]))
        else:
            socks._BaseSocket.close(self)
            raise error.SOCKSv5Error("SOCKS Server error.")
        boundport = struct.unpack(">H", socks._BaseSocket.recv(self, 2))[0]
        socks._BaseSocket.close(self)
        return ip


def torsocket(family=socket.AF_INET, type=socket.SOCK_STREAM,
              proto=0, _sock=None):
    """
    Factory function usable as a monkey-patch for socket.socket.
    """

    # Pass through local sockets.
    if family in _LOCAL_SOCKETS:
        return orig_socket(family, type, proto, _sock)

    # Tor only supports AF_INET sockets.
    if family != socket.AF_INET:
        raise socket.error(errno.EAFNOSUPPORT, os.strerror(errno.EAFNOSUPPORT))

    # Tor only supports SOCK_STREAM sockets.
    if type != socket.SOCK_STREAM:
        raise socket.error(errno.ESOCKTNOSUPPORT,
                           os.strerror(errno.ESOCKTNOSUPPORT))

    # Acceptable values for PROTO are 0 and IPPROTO_TCP.
    if proto not in (0, socket.IPPROTO_TCP):
        raise socket.error(errno.EPROTONOSUPPORT,
                           os.strerror(errno.EPROTONOSUPPORT))

    return _Torsocket(family, type, proto, _sock)

def getaddrinfo(*args):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (args[0], args[1]))]


class MonkeyPatchedSocket(object):
    """
    Context manager which monkey-patches socket.socket with
    the above torsocket().  It also sets up this module's
    global state.
    """
    def __init__(self, queue, circ_id, socks_port=9051, socks_addr="127.0.0.1"):
        self._queue           = queue
        self._circ_id         = circ_id
        self._socks_addr      = socks_addr
        self._socks_port      = socks_port

        self._orig_queue      = None
        self._orig_circ_id    = None
        self._orig_proxy_addr = None
        self._orig_proxy_port = None
        self._orig_socket     = None

    def __enter__(self):
        global queue, circ_id, proxy_addr, proxy_port, socket, torsocket

        # Make sure __exit__ can put everything back just as it was.
        self._orig_queue      = queue
        self._orig_circ_id    = circ_id
        self._orig_proxy_addr = proxy_addr
        self._orig_proxy_port = proxy_port
        self._orig_socket     = socket.socket

        queue                 = self._queue
        circ_id               = self._circ_id
        proxy_addr            = self._socks_addr
        proxy_port            = self._socks_port
        socks.set_default_proxy(socks.SOCKS5, proxy_addr, proxy_port, True, None, None)
        socket.socket         = torsocket
        socket.getaddrinfo    = getaddrinfo

        return self

    def __exit__(self, *dontcare):
        global queue, circ_id, proxy_addr, proxy_port, socket

        queue                 = self._orig_queue
        circ_id               = self._orig_circ_id
        proxy_addr            = self._orig_proxy_addr
        proxy_port            = self._orig_proxy_port
        socket.socket         = self._orig_socket
        socket.getaddrinfo    = _orig_getaddrinfo

        return False

