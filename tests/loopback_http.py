"""HTTP servers for tests that bind a loopback address without a host name lookup.

http.server's server_bind() calls socket.getfqdn() on the bound address. On GitHub's macOS runners that
reverse lookup of 127.0.0.1 takes about 35 s in every new process, so fake DevTools servers missed their
startup timeouts there while passing locally."""

import socketserver
from http.server import ThreadingHTTPServer


class LoopbackHTTPServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = str(host), port
