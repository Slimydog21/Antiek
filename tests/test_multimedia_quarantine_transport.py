from __future__ import annotations

import socket

import pytest

import substrate.multimedia.quarantine_transport as transport_module
from substrate.multimedia.quarantine_transport import PinnedTLSTransport, SocketResolver


def test_resolver_returns_bounded_unique_addresses(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ],
    )
    assert SocketResolver().resolve("cdn.example.test") == ("93.184.216.34",)


def test_pinned_transport_uses_direct_ip_sni_host_and_streams(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class Raw:
        def close(self): pass

    class Wrapped:
        def getpeername(self): return ("93.184.216.34", 443)
        def close(self): pass

    class Context:
        def wrap_socket(self, raw, *, server_hostname):
            observed["sni"] = server_hostname
            return Wrapped()

    class Response:
        status = 200
        chunks = [b"png", b""]
        def getheaders(self): return [("Content-Type", "image/png")]
        def read(self, _size): return self.chunks.pop(0)

    class Connection:
        def __init__(self, host, port, timeout):
            observed.update(host=host, port=port, timeout=timeout)
            self.sock = None
        def request(self, method, target, headers):
            observed.update(method=method, target=target, headers=headers)
        def getresponse(self): return Response()
        def close(self): observed["closed"] = True

    monkeypatch.setattr(
        socket, "create_connection",
        lambda address, timeout: observed.update(address=address) or Raw(),
    )
    monkeypatch.setattr(transport_module.http.client, "HTTPConnection", Connection)
    response = PinnedTLSTransport(ssl_context=Context()).get(
        url="https://cdn.example.test/image.png?x=1",
        pinned_ips=frozenset({"93.184.216.34"}),
        tls_hostname="cdn.example.test", timeout_seconds=7,
    )
    assert b"".join(response.body) == b"png"
    assert response.peer_ip == "93.184.216.34"
    assert observed == {
        "address": ("93.184.216.34", 443), "sni": "cdn.example.test",
        "host": "cdn.example.test", "port": 443, "timeout": 7,
        "method": "GET", "target": "/image.png?x=1",
        "headers": {
            "Accept": "image/png,image/jpeg,video/mp4", "Host": "cdn.example.test"
        },
        "closed": True,
    }


def test_pinned_transport_rejects_peer_drift(monkeypatch) -> None:
    class Raw:
        def close(self): pass
    class Wrapped:
        def getpeername(self): return ("93.184.216.35", 443)
        def close(self): pass
    class Context:
        def wrap_socket(self, raw, *, server_hostname): return Wrapped()
    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: Raw())
    with pytest.raises(RuntimeError, match="pinned"):
        PinnedTLSTransport(ssl_context=Context()).get(
            url="https://cdn.example.test/a.png",
            pinned_ips=frozenset({"93.184.216.34"}),
            tls_hostname="cdn.example.test", timeout_seconds=5,
        )
