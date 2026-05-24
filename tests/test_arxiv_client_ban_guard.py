"""
Tests that the arxiv client wires ban_state correctly.

This is the part that actually CLOSES the regression fixture: building
ban_state is necessary but not sufficient — the client's request
chokepoint (_http_get) must (1) refuse to issue a request while banned,
and (2) persist the ban on a 429 response. Without the wiring the
sentinel is inert.

Uses httpx.MockTransport so no network is touched. The injected client
path skips the SSL bootstrap (tests own their transport), so these tests
exercise the ban guards specifically.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e2-harness.html (E2 GAP closure)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from acquisition.arxiv import ban_state
from acquisition.arxiv.client import ArxivBanned, fetch_by_id, search

_VALID_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2511.00001v1</id>
    <title>A Test Paper</title>
    <summary>An abstract.</summary>
    <published>2026-05-01T00:00:00Z</published>
    <updated>2026-05-01T00:00:00Z</updated>
    <author><name>Ada Lovelace</name></author>
    <category term="cs.LG"/>
  </entry>
</feed>"""


@pytest.fixture
def sentinel(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "arxiv_banned_until.json"
    monkeypatch.setenv("ANTIEK_ARXIV_BAN_SENTINEL", str(p))
    return p


def _client_returning(status_code: int, content: bytes = b"") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=content)

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Guard 1 — refuse to request while banned
# ---------------------------------------------------------------------------


def test_search_raises_arxivbanned_when_banned(sentinel: Path) -> None:
    ban_state.mark_banned(until=datetime.now(timezone.utc) + timedelta(hours=1))
    # Even with a client that WOULD return 200, the guard fires first.
    client = _client_returning(200, _VALID_ATOM)
    with pytest.raises(ArxivBanned) as exc:
        search(query="test", client=client)
    assert exc.value.remaining_seconds > 0


def test_fetch_by_id_raises_arxivbanned_when_banned(sentinel: Path) -> None:
    ban_state.mark_banned(until=datetime.now(timezone.utc) + timedelta(hours=1))
    client = _client_returning(200, _VALID_ATOM)
    with pytest.raises(ArxivBanned):
        fetch_by_id("2511.00001", client=client)


def test_no_request_issued_while_banned(sentinel: Path) -> None:
    """The guard must fire BEFORE the transport is hit — prove the
    handler is never called."""
    ban_state.mark_banned(until=datetime.now(timezone.utc) + timedelta(hours=1))
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=_VALID_ATOM)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ArxivBanned):
        search(query="test", client=client)
    assert calls["n"] == 0, "request was issued despite an active ban"


# ---------------------------------------------------------------------------
# Guard 3 — capture a 429 into the sentinel
# ---------------------------------------------------------------------------


def test_429_marks_ban(sentinel: Path) -> None:
    assert ban_state.is_banned() is False
    client = _client_returning(429, b"rate limited")
    with pytest.raises(httpx.HTTPStatusError):
        search(query="test", client=client)
    # The 429 must have persisted the sentinel.
    assert ban_state.is_banned() is True
    assert ban_state.remaining() is not None


def test_429_then_subsequent_call_short_circuits(sentinel: Path) -> None:
    """End-to-end: a 429 bans, and the NEXT call short-circuits at
    Guard 1 without issuing a request. This is the re-trigger loop
    being broken."""
    # First call: 429 → ban persisted.
    client_429 = _client_returning(429, b"rate limited")
    with pytest.raises(httpx.HTTPStatusError):
        search(query="test", client=client_429)

    # Second call: even a healthy 200 client must not be reached.
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=_VALID_ATOM)

    healthy = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ArxivBanned):
        search(query="test", client=healthy)
    assert calls["n"] == 0


# ---------------------------------------------------------------------------
# Happy path — no ban, 200 works as before (no regression)
# ---------------------------------------------------------------------------


def test_search_works_normally_when_not_banned(sentinel: Path) -> None:
    client = _client_returning(200, _VALID_ATOM)
    papers = search(query="test", client=client)
    assert len(papers) == 1
    assert papers[0].arxiv_id == "2511.00001"
    # No ban side-effect from a successful call.
    assert ban_state.is_banned() is False


def test_404_does_not_mark_ban(sentinel: Path) -> None:
    """Only a 429 marks a ban — other errors must not."""
    client = _client_returning(404, b"not found")
    with pytest.raises(httpx.HTTPStatusError):
        search(query="test", client=client)
    assert ban_state.is_banned() is False
