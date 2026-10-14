import socket
from http.server import BaseHTTPRequestHandler

from loopback_http import LoopbackHTTPServer


def test_test_servers_bind_without_a_name_lookup(monkeypatch):
    def lookup(*args):
        raise AssertionError("the server looked up a host name")

    monkeypatch.setattr(socket, "getfqdn", lookup)
    server = LoopbackHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()
