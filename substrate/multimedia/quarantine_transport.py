"""DNS resolver and pinned-IP TLS transport for artifact quarantine."""

from __future__ import annotations

import http.client
import socket
import ssl
from collections.abc import Iterator
from urllib.parse import urlsplit

from .artifact_quarantine import TransportResponse


class SocketResolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        if not isinstance(hostname, str) or not hostname or len(hostname) > 253:
            raise ValueError("artifact hostname is invalid")
        try:
            answers = socket.getaddrinfo(
                hostname, 443, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
            )
        except OSError:
            raise RuntimeError("artifact DNS resolution failed") from None
        addresses = tuple(dict.fromkeys(str(row[4][0]) for row in answers))
        if not addresses or len(addresses) > 8:
            raise RuntimeError("artifact DNS resolution is unbounded")
        return addresses


class PinnedTLSTransport:
    def __init__(self, *, ssl_context: ssl.SSLContext | None = None) -> None:
        self._context = ssl_context or ssl.create_default_context()

    def get(
        self,
        *,
        url: str,
        pinned_ips: frozenset[str],
        tls_hostname: str,
        timeout_seconds: float,
    ) -> TransportResponse:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https" or parsed.hostname != tls_hostname
            or parsed.port not in {None, 443} or parsed.username or parsed.password
            or not pinned_ips or len(pinned_ips) > 8
        ):
            raise RuntimeError("artifact transport authority is invalid")
        target_ip = sorted(pinned_ips)[0]
        raw: socket.socket | None = None
        wrapped: ssl.SSLSocket | None = None
        connection: http.client.HTTPConnection | None = None
        try:
            raw = socket.create_connection((target_ip, 443), timeout=timeout_seconds)
            wrapped = self._context.wrap_socket(raw, server_hostname=tls_hostname)
            raw = None
            peer_ip = str(wrapped.getpeername()[0])
            if peer_ip not in pinned_ips:
                raise RuntimeError("artifact peer address was not pinned")
            connection = http.client.HTTPConnection(tls_hostname, 443, timeout=timeout_seconds)
            connection.sock = wrapped
            wrapped = None
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request(
                "GET", target,
                headers={"Accept": "image/png,image/jpeg,video/mp4", "Host": tls_hostname},
            )
            response = connection.getresponse()
            headers = {str(key): str(value) for key, value in response.getheaders()}
            content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            declared = headers.get("Content-Length")
            invalid_length = False
            if declared is not None:
                try:
                    invalid_length = int(declared) < 1 or int(declared) > 100 * 1024 * 1024
                except ValueError:
                    invalid_length = True
            if (
                response.status != 200
                or content_type not in {"image/png", "image/jpeg", "video/mp4"}
                or invalid_length
            ):
                connection.close()
                return TransportResponse(
                    status_code=int(response.status), headers=headers,
                    peer_ip=peer_ip, body=(),
                )

            def chunks() -> Iterator[bytes]:
                try:
                    while chunk := response.read(1024 * 1024):
                        yield chunk
                finally:
                    connection.close()

            return TransportResponse(
                status_code=int(response.status), headers=headers,
                peer_ip=peer_ip, body=chunks(),
            )
        except Exception:
            if connection is not None:
                connection.close()
            if wrapped is not None:
                wrapped.close()
            if raw is not None:
                raw.close()
            raise


__all__ = ["PinnedTLSTransport", "SocketResolver"]
