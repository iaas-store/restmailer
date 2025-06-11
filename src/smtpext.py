import smtplib
import socket
from ssl import SSLContext
from urllib.parse import urlparse, ParseResult

import socks


class SMTP(smtplib.SMTP):
    _host: str | None
    proxy_socket: socks.socksocket | None
    ssl_context: SSLContext | None

    def __init__(self, local_hostname: str, timeout: float):
        super().__init__(local_hostname=local_hostname, timeout=timeout)

    def enable_proxy(self, proxy_url: str) -> None:
        args = []
        url: ParseResult = urlparse(proxy_url)

        args.append({
            'http': socks.HTTP,
            'socks4': socks.SOCKS4,
            'socks5': socks.SOCKS5,
        }[url.scheme])

        args.append(url.hostname)
        args.append(url.port)
        args.append(True)
        args.append(url.username)
        args.append(url.password)

        self.proxy_socket = socks.socksocket()
        self.proxy_socket.set_proxy(*args)

    def connect(self, host: str = 'localhost', port: int = smtplib.SMTP_PORT, source_address=None):
        self._host = host
        self.ssl_context = None
        return super().connect(host, port)

    def connect_ssl(self, host: str = 'localhost', port: int = smtplib.SMTP_SSL_PORT, context: SSLContext = SSLContext()):
        self.ssl_context = context
        return self.connect(host, port)

    def _get_socket(self, host, port, timeout):
        sock = getattr(
            self,
            'proxy_socket',
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        )

        sock.settimeout(timeout)
        if isinstance(timeout, int):
            sock.settimeout(timeout)
        sock.connect((host, port))

        ssl_contest: SSLContext = getattr(self, 'ssl_context', None)
        if ssl_contest:
            ssl_contest.wrap_socket(sock, server_hostname=self._host)

        return sock



