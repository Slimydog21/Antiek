"""Tests for SPR-04 M1 — on-demand arXiv PDF fetch.

NO live HTTP: every request goes through an ``httpx.MockTransport`` handler. The
throttle is pointed at a tmp state file (``ANTIEK_ARXIV_THROTTLE_PATH``) with a
no-op sleep + a fake clock, so tests are fast and never touch the real sentinel.

Edge cases asserted here:
  - a valid %PDF body → FetchedPdf with the right sha256 / byte_size / source_url
  - an HTML interstitial served 200 → NotAPdf (the connector-resilience precheck)
  - a 429 → the throttle records the ban sentinel; a SECOND fetch raises
    ArxivBanned WITHOUT a second send (the ban is honored, no retry)
  - a 404 (withdrawn id) → HTTPStatusError, no body fabricated
  - an implausibly small body that still starts %PDF → PdfTooSmall
  - >3s spacing is enforced between two fetches (the persisted throttle)
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.pdf_fetch import (  # noqa: E402
    MIN_PDF_BYTES,
    ArxivBanned,
    NotAPdf,
    PdfTooLarge,
    PdfTooSmall,
    fetch_pdf,
)
from acquisition.arxiv.throttle import ArxivThrottle  # noqa: E402

# A valid (tiny) PDF body — passes the %PDF magic-byte check and the size floor.
_VALID_PDF = b"%PDF-1.4\n" + b"x" * (MIN_PDF_BYTES + 64)
_HTML_INTERSTITIAL = b"<!doctype html>\n<html><body>Paper withdrawn</body></html>"


class _FakeClock:
    """A monotonic fake clock the throttle reads via ``now`` and advances via
    the no-op ``sleep`` — so >=3s spacing is exercised without real waiting."""

    def __init__(self) -> None:
        self.t = 1000.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def throttle(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_ARXIV_THROTTLE_PATH", str(tmp_path / "throttle.json"))
    clock = _FakeClock()
    t = ArxivThrottle(
        state_path=str(tmp_path / "throttle.json"),
        now=clock.now,
        sleep=clock.sleep,
    )
    t._clock = clock  # type: ignore[attr-defined]  # for tests to read/advance
    return t


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_pdf_fetch_returns_verified_bytes(throttle):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        return httpx.Response(
            200, content=_VALID_PDF, headers={"content-type": "application/pdf"}
        )

    with _client(handler) as c:
        fetched = fetch_pdf("2402.00001", throttle=throttle, client=c)

    assert seen["url"] == "https://arxiv.org/pdf/2402.00001"
    assert fetched.content == _VALID_PDF
    assert fetched.byte_size == len(_VALID_PDF)
    assert fetched.source_url == "https://arxiv.org/pdf/2402.00001"
    import hashlib

    assert fetched.sha256 == hashlib.sha256(_VALID_PDF).hexdigest()


def test_pdf_with_no_content_type_still_accepted_on_magic_bytes(throttle):
    """A response with no content-type header but valid %PDF bytes is accepted —
    the magic-byte check is the authoritative signal."""
    def handler(req): return httpx.Response(200, content=_VALID_PDF)
    with _client(handler) as c:
        fetched = fetch_pdf("2402.00009", throttle=throttle, client=c)
    assert fetched.byte_size == len(_VALID_PDF)


# ---------------------------------------------------------------------------
# %PDF precheck — HTML interstitial rejected
# ---------------------------------------------------------------------------


def test_html_interstitial_is_not_a_pdf(throttle):
    def handler(req):
        return httpx.Response(
            200, content=_HTML_INTERSTITIAL, headers={"content-type": "text/html"}
        )

    with _client(handler) as c, pytest.raises(NotAPdf):
        fetch_pdf("2402.00002", throttle=throttle, client=c)


def test_html_body_without_content_type_rejected_on_magic_bytes(throttle):
    """Even with no content-type, an HTML body fails the %PDF magic-byte check."""
    def handler(req): return httpx.Response(200, content=_HTML_INTERSTITIAL)
    with _client(handler) as c, pytest.raises(NotAPdf):
        fetch_pdf("2402.00010", throttle=throttle, client=c)


# ---------------------------------------------------------------------------
# Size guards
# ---------------------------------------------------------------------------


def test_too_small_pdf_rejected(throttle):
    tiny = b"%PDF-1.4\n"  # starts %PDF but far under MIN_PDF_BYTES
    def handler(req):
        return httpx.Response(200, content=tiny, headers={"content-type": "application/pdf"})
    with _client(handler) as c, pytest.raises(PdfTooSmall):
        fetch_pdf("2402.00003", throttle=throttle, client=c)


def test_too_large_pdf_rejected(throttle):
    def handler(req):
        return httpx.Response(
            200, content=_VALID_PDF, headers={"content-type": "application/pdf"}
        )
    with _client(handler) as c, pytest.raises(PdfTooLarge):
        fetch_pdf("2402.00004", throttle=throttle, client=c, max_bytes=8)


def test_size_guards_subclass_not_a_pdf(throttle):
    """PdfTooSmall/PdfTooLarge subclass NotAPdf so a caller branching on
    'not a usable PDF' catches them without a separate except clause."""
    assert issubclass(PdfTooSmall, NotAPdf)
    assert issubclass(PdfTooLarge, NotAPdf)


# ---------------------------------------------------------------------------
# HTTP errors — no fabricated body
# ---------------------------------------------------------------------------


def test_404_withdrawn_id_raises_status_error(throttle):
    def handler(req):
        return httpx.Response(404, content=b"not found")
    with _client(handler) as c, pytest.raises(httpx.HTTPStatusError):
        fetch_pdf("2402.00005", throttle=throttle, client=c)


# ---------------------------------------------------------------------------
# Ban sentinel honored — 429 then no retry
# ---------------------------------------------------------------------------


def test_429_records_ban_and_second_fetch_raises_without_send(throttle):
    sends = {"count": 0}

    def handler(req):
        sends["count"] += 1
        return httpx.Response(429, headers={"Retry-After": "1800"})

    with _client(handler) as c:
        # First fetch: the 429 raises HTTPStatusError (raise_for_status) AND the
        # throttle's note_response records banned_until from Retry-After.
        with pytest.raises(httpx.HTTPStatusError):
            fetch_pdf("2402.00006", throttle=throttle, client=c)
        assert sends["count"] == 1
        assert throttle.is_banned()

        # Second fetch: the ban sentinel is active → ArxivBanned BEFORE any send.
        with pytest.raises(ArxivBanned):
            fetch_pdf("2402.00006", throttle=throttle, client=c)
        # No second HTTP send happened — the ban was honored, not retried.
        assert sends["count"] == 1


def test_active_ban_blocks_fetch_entirely(throttle):
    """A pre-existing ban (set before any request) blocks the very first fetch."""
    throttle.note_response(429, {"Retry-After": "600"})

    def handler(req):  # pragma: no cover - must not run
        raise AssertionError("fetch ran despite an active ban")

    with _client(handler) as c, pytest.raises(ArxivBanned):
        fetch_pdf("2402.00007", throttle=throttle, client=c)


# ---------------------------------------------------------------------------
# Spacing — the persisted throttle enforces >=3s between fetches
# ---------------------------------------------------------------------------


def test_two_fetches_space_by_at_least_three_seconds(throttle):
    clock = throttle._clock  # type: ignore[attr-defined]

    def handler(req):
        return httpx.Response(
            200, content=_VALID_PDF, headers={"content-type": "application/pdf"}
        )

    with _client(handler) as c:
        t0 = clock.now()
        fetch_pdf("2402.00008a", throttle=throttle, client=c)
        fetch_pdf("2402.00008b", throttle=throttle, client=c)
        # The no-op sleep advanced the fake clock by the spacing debt.
        assert clock.now() - t0 >= 3.0
