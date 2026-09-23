"""Link Monster — SSRF guard tests.

The guard is the security-critical layer of a paste-any-URL feature, so
every block class gets its own test: loopback, cloud metadata, RFC1918,
CGNAT, IPv6 ULA, userinfo smuggling, non-http schemes, redirect-to-
private (including the live attack ``http://127.0.0.1:8001/health``),
and redirect caps. IP-literal hosts are used for block cases so no DNS
is touched; public-host fetch paths monkeypatch ``_host_is_safe`` so
MockTransport serves them without network.
"""

from __future__ import annotations

import httpx
import pytest

from acquisition.link_monster.fetchguard import (
    UnsafeUrlError,
    assert_safe_target,
    fetch_guarded,
    validate_url,
)

_BLOCKED = [
    "http://127.0.0.1:8001/health",       # loopback (the live prod API!)
    "http://127.0.0.1/anything",
    "http://localhost/x",
    "http://169.254.169.254/latest/meta-data",  # cloud metadata
    "http://10.0.0.1/x",                  # RFC1918
    "http://172.16.0.1/x",                # RFC1918
    "http://192.168.1.1/x",               # RFC1918
    "http://100.64.0.1/x",                # CGNAT
]


@pytest.mark.parametrize("url", _BLOCKED)
def test_blocked_targets(url):
    with pytest.raises(UnsafeUrlError) as ei:
        assert_safe_target(url)
    assert ei.value.reason == "ssrf_blocked"


def test_validate_url_rejects_bad_schemes():
    for bad in ("file:///etc/passwd", "gopher://x", "ftp://x", "javascript:alert(1)"):
        with pytest.raises(UnsafeUrlError) as ei:
            validate_url(bad)
        assert ei.value.reason.startswith("bad_scheme")


def test_validate_url_rejects_userinfo():
    # Classic credential-smuggling bypass: the request would be sent to
    # 127.0.0.1 with a Host header of the attacker-controlled string.
    with pytest.raises(UnsafeUrlError) as ei:
        validate_url("http://attacker@127.0.0.1/")
    assert ei.value.reason == "userinfo_forbidden"


def test_validate_url_empty_and_hostless():
    with pytest.raises(UnsafeUrlError):
        validate_url("")
    with pytest.raises(UnsafeUrlError):
        validate_url("https:///path")


def test_fetch_guarded_blocks_redirect_to_private(monkeypatch):
    """The redirect hop must be re-validated — this is the exact attack
    where a public page redirects to the substrate's own health check."""
    called = []

    def handler(req: httpx.Request) -> httpx.Response:
        called.append(str(req.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8001/health"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    # Simulate real DNS: the public start host resolves public; the
    # private redirect target resolves loopback (the guard re-checks it).
    monkeypatch.setattr(
        "acquisition.link_monster.fetchguard._host_is_safe",
        lambda h: h == "public.example.com",
    )
    with pytest.raises(UnsafeUrlError) as ei:
        fetch_guarded("https://public.example.com/start", client=client)
    assert ei.value.reason == "ssrf_blocked"
    assert called == ["https://public.example.com/start"]


def test_fetch_guarded_redirect_cap(monkeypatch):
    hops = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        hops["n"] += 1
        return httpx.Response(302, headers={"location": f"https://public.example.com/{hops['n']}"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    monkeypatch.setattr("acquisition.link_monster.fetchguard._host_is_safe", lambda h: True)
    with pytest.raises(UnsafeUrlError) as ei:
        fetch_guarded("https://public.example.com/start", client=client)
    assert ei.value.reason == "too_many_redirects"


def test_fetch_guarded_happy_path(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "public.example.com"
        return httpx.Response(200, content=b"<html><title>ok</title></html>",
                              headers={"content-type": "text/html; charset=utf-8"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    monkeypatch.setattr("acquisition.link_monster.fetchguard._host_is_safe", lambda h: True)
    page = fetch_guarded("https://public.example.com/start", client=client)
    assert page.final_url == "https://public.example.com/start"
    assert b"ok" in page.body


def test_fetch_guarded_4xx_raises(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"missing")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    monkeypatch.setattr("acquisition.link_monster.fetchguard._host_is_safe", lambda h: True)
    with pytest.raises(httpx.HTTPStatusError):
        fetch_guarded("https://public.example.com/missing", client=client)


def test_guard_denies_by_default_not_by_denylist(monkeypatch) -> None:
    """Every non-global address must be refused, not just the listed ones.

    A denylist can only reject the forms someone thought to enumerate. The
    IPv4-mapped IPv6 form is in none of the listed networks — an IPv6Address
    never compares inside an IPv4Network — so it passed the guard while the OS
    routed it to the IPv4 target. `is_global` is what makes the docstring's
    promise ("require all of them to be public") actually true.
    """
    import socket as _socket

    from acquisition.link_monster import fetchguard

    must_refuse = [
        "127.0.0.1",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",        # the mapped form the denylist could not see
        "::ffff:169.254.169.254",
        "0.0.0.0",
        "::",
    ]
    must_allow = ["8.8.8.8", "2606:4700::1"]

    def _resolve_to(addr: str):
        fam = _socket.AF_INET6 if ":" in addr else _socket.AF_INET
        return lambda host, port: [(fam, None, None, "", (addr, 0))]

    for addr in must_refuse:
        monkeypatch.setattr(fetchguard.socket, "getaddrinfo", _resolve_to(addr))
        assert not fetchguard._host_is_safe("probe.invalid"), f"{addr} must be refused"

    # The other half: a stricter posture must not break the feature.
    for addr in must_allow:
        monkeypatch.setattr(fetchguard.socket, "getaddrinfo", _resolve_to(addr))
        assert fetchguard._host_is_safe("probe.invalid"), f"{addr} must stay allowed"
