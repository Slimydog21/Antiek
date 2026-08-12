"""SSRF guard for the doc-ingest source_url download path (CWE-918).

The ingest route downloads an operator-supplied ``source_url``. Without a
guard, an authenticated caller can point that fetch at loopback, cloud
metadata (169.254.169.254), or other internal services and ingest the
response as a document. This module validates every URL BEFORE each fetch
hop (including redirects, which are re-validated, never blindly followed).

Guard posture (v1, honest residual):
- scheme must be http/https; no userinfo; no non-global literal IPs;
- hostnames resolve to AT LEAST one address and EVERY resolved address
  must be globally routable (``ipaddress.is_global`` — the same idiom as
  ``substrate.multimedia.provider_recovery_adapter._endpoint``);
- redirects are followed manually, max 3 hops, each hop re-validated.
- RESIDUAL: the connection is not pinned to the validated IP (DNS
  rebinding between validate and connect is theoretically possible).
  Pinning requires an IP-connect + Host-header transport with SNI
  handling; deferred as a hardening sprint. Single-operator + auth +
  invite-only v1 makes the residual acceptable; revisit before public
  beta.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

_MAX_REDIRECTS = 3
_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost", ".localdomain", ".lan")

Resolver = Callable[[str], list[tuple]]


class SsrfError(ValueError):
    """The candidate URL is not a safe public http(s) target."""


def validate_public_http_url(
    url: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> str:
    """Validate a source URL for public http(s) fetch; return it stripped.

    Raises SsrfError when the URL is not a safe public target. The
    resolver is injectable for hermetic tests.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise SsrfError("only http/https source URLs are allowed")
    if parts.username is not None or parts.password is not None:
        raise SsrfError("URLs with embedded credentials are not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise SsrfError("source URL has no host")
    if host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise SsrfError("non-public host is not allowed")
    if parts.port is not None and not (1 <= parts.port <= 65535):
        raise SsrfError("invalid port")
    if "/" in host:
        raise SsrfError("invalid host")

    # Literal IPs must be globally routable.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not addr.is_global:
            raise SsrfError("non-public IP is not allowed")

    # Hostname: every resolved address must be global.
    try:
        infos = resolver(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise SsrfError(f"host does not resolve: {host}") from exc
    addrs = {info[4][0] for info in infos}
    if not addrs:
        raise SsrfError(f"host does not resolve: {host}")
    for raw in addrs:
        candidate = raw.split("%")[0]  # strip IPv6 scope id
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError as exc:
            raise SsrfError(f"host resolved to a non-IP: {raw}") from exc
        if not ip.is_global:
            raise SsrfError(f"host resolves to a non-public address: {raw}")
    return url.strip()


__all__ = ["SsrfError", "validate_public_http_url", "_MAX_REDIRECTS"]
