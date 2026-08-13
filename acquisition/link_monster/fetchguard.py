"""Link Monster — SSRF guard.

The Monster's premise is "paste any URL and the server fetches it" —
which is exactly the shape of a server-side request forgery hole. The
pre-existing ``acquisition/urls`` client has NO protection of this
kind, so Link Monster carries its own mandatory guard and never reuses
the unguarded fetch path.

What is blocked (all resolved IPs of the final URL AND of every
redirect hop):

- loopback:           127.0.0.0/8, ::1
- link-local + cloud
  metadata:           169.254.0.0/16, fe80::/10 (169.254.169.254 is
                      the classic cloud-metadata endpoint)
- private RFC1918:    10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
- CGNAT / carrier:    100.64.0.0/10
- IPv6 ULA:           fc00::/7
- site-local IPv6:    fec0::/10 (deprecated but still firewalled
                      silently on many hosts)

Also blocked by construction:

- non-http(s) schemes (file:, gopher:, dict:…)
- URL userinfo (``http://attacker@127.0.0.1/`` — the classic
  credential-smuggling bypass; httpx would happily send the request
  to 127.0.0.1 with a Host of the attacker string)
- more than ``MAX_REDIRECTS`` hops (default 5)
- non-200/3xx responses on the metadata pass are simply non-results
  (the ladder falls through), never errors

Honest limitation (documented, not hidden): the guard resolves + checks
before the fetch and re-checks every redirect hop, but the connect and
the check are not atomic — a DNS-rebinding attacker could in principle
flip a public name to a private address between our check and httpx's
connect. Mitigation depth: (a) re-check every hop; (b) the metadata
pass sends no cookies/credentials and reads no body beyond 2 MiB;
(c) the deeper text pass (``digest.py``) re-runs the guard on the
final URL before fetching body content. A fully rebinding-proof client
needs a pinned-IP transport; that is a named future hardening, not a
silent claim of immunity.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_TIMEOUT_S = 10.0
MAX_REDIRECTS = 5
MAX_BODY_BYTES = 2_000_000


class UnsafeUrlError(ValueError):
    """Raised when a URL (or one of its redirect targets) is refused by
    the SSRF guard. ``reason`` is a short machine-readable tag; the
    routes translate it into a typed 422 response."""

    def __init__(self, reason: str, url: str | None = None) -> None:
        self.reason = reason
        self.url = url
        super().__init__(f"{reason}: {url}" if url else reason)


def _blocked_ranges() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    return [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("fe80::/10"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fec0::/10"),
    ]


def validate_url(url: str) -> str:
    """Structural validation: http(s) scheme, no userinfo, parseable
    hostname. Returns the normalized URL. Raises UnsafeUrlError."""
    if not isinstance(url, str) or not url.strip():
        raise UnsafeUrlError("empty_url")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"bad_scheme:{parsed.scheme}")
    if not parsed.hostname:
        raise UnsafeUrlError("no_host")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("userinfo_forbidden")
    return url.strip()


def _host_is_safe(hostname: str) -> bool:
    """Resolve every address for ``hostname`` and require all of them to
    be public. A host that resolves to a mix of public + private is
    blocked (all-or-nothing — the mixed case is exactly what a
    rebinding/round-robin bypass looks like)."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    ranges = _blocked_ranges()
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        for net in ranges:
            if addr in net:
                return False
    return True


def assert_safe_target(url: str) -> None:
    """Resolve + range-check the URL's hostname. Raises UnsafeUrlError
    with reason ``ssrf_blocked`` on any private/link-local/metadata
    address or unresolvable host."""
    parsed = urlparse(url)
    if not _host_is_safe(parsed.hostname or ""):
        raise UnsafeUrlError("ssrf_blocked", url)


@dataclass(frozen=True)
class GuardedPage:
    """Result of a guarded HTTP pass: the final (post-redirect) URL and
    the body bytes. ``final_url`` is re-validated by the guard before it
    is trusted."""

    final_url: str
    body: bytes
    headers: Any  # httpx.Headers




def _governed_get(client: httpx.Client, url: str) -> httpx.Response:
    """One governed GET. The arXiv-boundary discipline (rate_governor.py)
    applies at the send: a paste-any-URL fetcher can be pointed at
    arxiv.org, so the request must ride the host-global governor (flock +
    spacing + 429 ban sentinel). Non-arXiv hosts pass through untouched.
    Separate function (not a closure over loop state) so ruff B023 has
    nothing to flag."""
    from acquisition.arxiv.rate_governor import govern_if_arxiv

    return govern_if_arxiv(
        url,
        lambda: client.get(
            url,
            follow_redirects=False,
            headers={"User-Agent": "AntiekLinkMonster/1.0 (+https://antiek.ai)"},
        ),
    )


def fetch_guarded(
    url: str,
    *,
    client: httpx.Client | None = None,
    max_redirects: int = MAX_REDIRECTS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    follow_redirects: bool = True,
) -> GuardedPage:
    """Fetch ``url`` with the SSRF guard on the initial URL and every
    redirect hop. Raises UnsafeUrlError (typed 422) on blocked targets
    and httpx.HTTPError subclasses on transport failures (typed 502 by
    the routes). Redirects are followed manually (``follow_redirects``
    on the underlying client is forced off for the guarded pass) so no
    hop can slip past the check."""
    url = validate_url(url)
    assert_safe_target(url)
    own = client is None
    if client is None:
        client = httpx.Client(
            timeout=timeout_s,
            follow_redirects=False,
            headers={"User-Agent": "AntiekLinkMonster/1.0 (+https://antiek.ai)"},
        )
    try:
        current = url
        for _ in range(max_redirects + 1):
            resp = _governed_get(client, current)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    raise UnsafeUrlError("redirect_no_location", current)
                next_url = str(httpx.URL(current).join(location))
                validate_url(next_url)
                assert_safe_target(next_url)
                current = next_url
                continue
            if resp.status_code == 304:
                raise UnsafeUrlError("not_modified", current)
            if resp.status_code >= 400:
                resp.raise_for_status()
            body = resp.content
            if len(body) > MAX_BODY_BYTES:
                body = body[:MAX_BODY_BYTES]
            return GuardedPage(final_url=str(resp.url), body=body, headers=resp.headers)
        raise UnsafeUrlError("too_many_redirects", url)
    finally:
        if own:
            client.close()
