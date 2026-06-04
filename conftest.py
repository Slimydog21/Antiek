"""Repo-root pytest conftest — the CI socket guard (Reader SPR-02 / DN1).

WHY THIS EXISTS
===============
The arXiv ingest family fetches structured documents from ``ar5iv`` and PDFs
from ``arxiv.org`` — both members of the arxiv.org host family that was once
429-BANNED (``acquisition/arxiv/source_document.py``; project memory). The ban
"must NOT recur," so the test suite must NEVER open a real socket to arXiv (or
anywhere else on the public internet).

Round 2 of SPR-02 flipped ``ingest_paper``'s ``emit_structured_blocks`` default
to ``True``. Six legacy call sites in ``tests/test_acquisition_arxiv.py`` — which
are NOT testing the structured-block column — silently started dialing
``ar5iv.labs.arxiv.org`` live (~4s/call, GET logged). They still PASSED (no
``structured_blocks`` assertion + a best-effort ``except`` that swallowed the
fetch), so the leak was invisible. A passing test that quietly hits a banned
endpoint is the worst kind of green.

WHAT THIS DOES
==============
An autouse fixture (active for every collected test, in every xdist worker)
replaces the connect primitives so any attempt to open a socket to a
NON-loopback address RAISES ``BlockedNetworkAccess`` loudly instead of dialing
out. So if a future default-egress regression leaks live arXiv into CI again,
the suite FAILS at the connect — it cannot silently ban us a second time.

Loopback (``127.0.0.0/8``, ``::1``, ``AF_UNIX``) is ALLOWED so that:
  * FastAPI ``TestClient`` / httpx ``MockTransport`` (in-process ASGI, no real
    socket) keep working;
  * tests that bind a real localhost server keep working;
  * pytest-xdist worker IPC keeps working.

OPT-OUT (rare): a test that genuinely needs real outbound network marks itself
``@pytest.mark.integration`` (the existing marker in ``pyproject.toml``) or
``@pytest.mark.allow_network``. Neither is used by the default suite today —
the allow-list is empty by design, which is what "ZERO outbound connections"
means.

This is a self-contained guard (no new dependency like ``pytest-socket``): it
patches ``socket.socket.connect`` / ``connect_ex`` and ``socket.create_connection``
at the stdlib boundary, which every HTTP client (httpx, urllib, requests, the
arXiv governed client) ultimately routes through.
"""

from __future__ import annotations

import socket as _socket_mod

import pytest

# The marker names that opt a test OUT of the guard. ``integration`` already
# exists in pyproject's [tool.pytest.ini_options].markers; ``allow_network`` is
# the explicit, single-purpose escape hatch registered below.
_NETWORK_OPT_OUT_MARKERS = ("integration", "allow_network")


class BlockedNetworkAccess(RuntimeError):
    """Raised when a test tries to open a real (non-loopback) socket.

    Seeing this in a traceback means a test reached for the public internet —
    almost always a live-arXiv leak. Either the call should be stubbed/injected
    (the norm — see ``fetch_structured=`` / ``fetch_pdf=`` / ``fetched=`` seams),
    or, if the test genuinely needs the network, mark it
    ``@pytest.mark.integration`` (it will then be excluded from the offline CI
    run)."""


def pytest_configure(config: pytest.Config) -> None:
    # Register the opt-out marker so ``--strict-markers`` (set in addopts) does
    # not reject ``@pytest.mark.allow_network``.
    config.addinivalue_line(
        "markers",
        "allow_network: test legitimately opens real outbound sockets; "
        "exempt from the SPR-02 CI socket guard (use sparingly).",
    )


def _is_loopback_host(host: object) -> bool:
    """True for addresses we always allow (loopback + Unix sockets).

    ``host`` is whatever landed in ``address[0]`` of a ``connect`` target. For
    ``AF_UNIX`` the address is a path string (or bytes), which we allow. For
    ``AF_INET`` / ``AF_INET6`` it is an IP/hostname string; we allow only the
    loopback range and the conventional localhost names."""
    if not isinstance(host, str):
        # AF_UNIX path can be bytes; allow. Anything non-str/bytes → not a
        # public-internet INET target, allow (e.g. abstract namespace).
        return True
    h = host.strip().strip("[]").lower()
    if h in ("localhost", "::1", "0.0.0.0", ""):  # noqa: S104 — match-only, not a bind
        return True
    if h.startswith("127."):
        return True
    if h.startswith("::ffff:127."):  # IPv4-mapped loopback
        return True
    return False


def _blocked(where: str, address: object) -> "BlockedNetworkAccess":
    return BlockedNetworkAccess(
        f"Outbound network blocked by the SPR-02 CI socket guard "
        f"({where} -> {address!r}). A test reached the public internet — this "
        f"is how the arXiv 429-ban recurs. Stub/inject the fetch (fetch_structured="
        f"/fetch_pdf=/fetched=), or mark the test @pytest.mark.integration if it "
        f"truly needs the network."
    )


@pytest.fixture(autouse=True)
def _block_outbound_network(request: pytest.FixtureRequest, monkeypatch):
    """Block real outbound sockets for the duration of every test.

    Patches the stdlib connect primitives so every HTTP client (httpx, urllib,
    the arXiv governed client) that ultimately calls ``socket.connect`` is gated.
    Loopback is allowed; opt-out markers disable the guard for the marked test.
    ``monkeypatch`` auto-reverts at teardown, so the guard is scoped per-test and
    leaves the interpreter clean between tests."""
    for marker in _NETWORK_OPT_OUT_MARKERS:
        if request.node.get_closest_marker(marker) is not None:
            return  # this test opted out — leave real sockets in place

    real_connect = _socket_mod.socket.connect
    real_connect_ex = _socket_mod.socket.connect_ex
    real_create_connection = _socket_mod.create_connection

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) and address else address
        if not _is_loopback_host(host):
            raise _blocked("socket.connect", address)
        return real_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) and address else address
        if not _is_loopback_host(host):
            raise _blocked("socket.connect_ex", address)
        return real_connect_ex(self, address, *args, **kwargs)

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) and address else address
        if not _is_loopback_host(host):
            raise _blocked("socket.create_connection", address)
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(_socket_mod.socket, "connect", guarded_connect)
    monkeypatch.setattr(_socket_mod.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(_socket_mod, "create_connection", guarded_create_connection)
    yield
