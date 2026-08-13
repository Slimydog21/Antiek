"""Tests for the HTML-first arXiv fetch (acquisition.arxiv.html_fetch).

NO live HTTP: every request goes through an ``httpx.MockTransport`` handler; the
throttle is a tmp-file-backed ``ArxivThrottle`` with a fake clock + no-op sleep,
mirroring test_arxiv_pdf_fetch. Asserts:
  - a real HTML rendering → FetchedHtml, article-sliced, correct sha256/char_count
  - page chrome outside <article> is stripped
  - a short / "no html" stub → None (caller falls back to PDF)
  - a 404 (no HTML rendering) → None, NOT an exception
  - a 429 → the ban sentinel is recorded and a SECOND fetch raises ArxivBanned
    WITHOUT a second send (rate discipline propagates; PDF fallback does not mask it)
"""

from __future__ import annotations

import hashlib
import os
import sys

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.html_fetch import (  # noqa: E402
    MIN_HTML_CHARS,
    ArxivBanned,
    fetch_html,
    slice_article,
)
from acquisition.arxiv.throttle import ArxivThrottle  # noqa: E402

# A real-looking arXiv LaTeXML page: chrome + <article> body + chrome. The article
# body alone is padded past MIN_HTML_CHARS so it is not treated as a stub.
_ARTICLE_BODY = "<p>" + ("Attention is all you need. " * 400) + "</p>"
_FULL_PAGE = (
    "<!doctype html><html><head><title>x</title></head><body>"
    "<nav>arXiv nav bar — Report GitHub Issue — nonprofit banner</nav>"
    f'<article class="ltx_document">{_ARTICLE_BODY}</article>'
    "<footer>arxiv footer chrome</footer>"
    "</body></html>"
).encode()

_STUB_PAGE = b"<!doctype html><html><body>No HTML version available for this paper.</body></html>"


class _FakeClock:
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
    t._clock = clock  # type: ignore[attr-defined]
    return t


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_slice_article_strips_chrome():
    sliced = slice_article(_FULL_PAGE.decode("utf-8"))
    assert "ltx_document" in sliced
    assert "Attention is all you need" in sliced
    assert "nav bar" not in sliced
    assert "footer chrome" not in sliced


def test_slice_article_passthrough_when_no_marker():
    raw = "<html><body>plain page, no article element</body></html>"
    assert slice_article(raw) == raw


def test_valid_html_fetch_returns_sliced_body(throttle):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        return httpx.Response(200, content=_FULL_PAGE, headers={"content-type": "text/html"})

    with _client(handler) as c:
        fetched = fetch_html("2402.00001", throttle=throttle, client=c)

    assert fetched is not None
    assert seen["url"] == "https://arxiv.org/html/2402.00001"
    assert fetched.source_url == "https://arxiv.org/html/2402.00001"
    assert "nav bar" not in fetched.html  # chrome stripped
    assert "Attention is all you need" in fetched.html
    assert fetched.char_count == len(fetched.html)
    assert fetched.sha256 == hashlib.sha256(fetched.html.encode("utf-8")).hexdigest()
    assert fetched.byte_size == len(fetched.html.encode("utf-8"))


def test_stub_page_returns_none(throttle):
    def handler(req):
        return httpx.Response(200, content=_STUB_PAGE, headers={"content-type": "text/html"})

    with _client(handler) as c:
        assert fetch_html("2402.00002", throttle=throttle, client=c) is None


def test_short_body_below_min_chars_returns_none(throttle):
    short = ("<article>" + "x" * (MIN_HTML_CHARS - 200) + "</article>").encode("utf-8")

    def handler(req):
        return httpx.Response(200, content=short, headers={"content-type": "text/html"})

    with _client(handler) as c:
        assert fetch_html("2402.00003", throttle=throttle, client=c) is None


def test_404_no_html_rendering_returns_none_not_raises(throttle):
    def handler(req):
        return httpx.Response(404, content=b"not found", headers={"content-type": "text/html"})

    with _client(handler) as c:
        # 404 = no HTML rendering; caller falls back to PDF, so None (no raise).
        assert fetch_html("2402.00004", throttle=throttle, client=c) is None


def test_429_records_ban_and_second_fetch_raises_without_send(throttle):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, content=b"rate limited", headers={"retry-after": "60"})

    with _client(handler) as c:
        # First fetch: 429 → the ban sentinel is recorded, mapped to None (PDF
        # fallback) is NOT what happens — a 429 is a ban signal via ArxivBanned.
        with pytest.raises(ArxivBanned):
            fetch_html("2402.00005", throttle=throttle, client=c)
        first = calls["n"]
        # Second fetch while banned: raises ArxivBanned BEFORE any new send.
        with pytest.raises(ArxivBanned):
            fetch_html("2402.00006", throttle=throttle, client=c)
    assert calls["n"] == first  # no second network send during the ban
