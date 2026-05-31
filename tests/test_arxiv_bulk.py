"""SPR-03 M4 — arXiv BULK-dataset path dodges the export-API 429.

The 2026-05-29 prod run's box IP was 429-banned by export.arxiv.org. For mass
volume the bulk path discovers candidates from the LOCAL Kaggle/GCS metadata
snapshot (arxiv-metadata-oai-snapshot.json, JSON-Lines) and NEVER touches the
export API. These tests prove:

  - the bulk path yields ArxivPaper candidates from a few-record fixture;
  - the export endpoint is NEVER called on the bulk path (the rigor-card
    assertion: a sentinel patched over the export client raises if hit);
  - the snapshot is iterated as a STREAM (a counting file object proves
    line-by-line consumption, not full materialization);
  - candidate shape matches the export adapter (same fields, license anchor);
  - the per-PDF fetch reuses the SourceThrottle (arxiv_pdf key) + the shared
    assert_pdf PDF-vs-HTML check (a landing page is a counted NotAPdf; a
    banned host raises SourceBanned without fetching).

NO live HTTP: the per-PDF fetch uses httpx.MockTransport; the snapshot is a
tmp file.
"""

from __future__ import annotations

import io
import json
import os
import sys

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv import bulk  # noqa: E402
from acquisition.arxiv.client import ArxivPaper  # noqa: E402
from acquisition.arxiv.throttle import ArxivThrottle  # noqa: E402
from acquisition.openaccess.pdf_detect import NotAPdf  # noqa: E402
from substrate.source_throttle import (  # noqa: E402
    SourceBanned,
    SourceThrottle,
)


def _isolated_arxiv_throttle(tmp_path, monkeypatch) -> ArxivThrottle:
    """Build an arXiv host-global governor throttle pointed at a TMP state file
    with a fake clock + no-op sleep + zero spacing, and point the governor flock
    at a tmp lock — so ``fetch_bulk_pdf``'s host-global arXiv governance is
    exercised WITHOUT touching the real ``~/.antiek/arxiv_throttle.json`` /
    ``.governor.lock`` and without a real 3s sleep. ``paper.pdf_url`` is an
    ``arxiv.org`` host, so ``govern_if_arxiv`` engages this throttle for real."""
    monkeypatch.setenv(
        "ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", str(tmp_path / "arxiv.governor.lock")
    )
    return ArxivThrottle(
        state_path=str(tmp_path / "arxiv_throttle.json"),
        min_spacing_s=0.0,
        now=lambda: 1000.0,
        sleep=lambda _s: None,
    )


# Two records in the documented Kaggle snapshot shape (trimmed to the
# load-bearing fields). One CC-BY (servable rights anchor), one no-license.
_RECORDS = [
    {
        "id": "2401.00001",
        "title": "A Bulk\n  Discovered Paper",
        "abstract": "We study   something\nmeaningful about systems.",
        "categories": "cs.LG cs.AI",
        "license": "http://creativecommons.org/licenses/by/4.0/",
        "authors": "Ada Lovelace and Alan Turing",
        "authors_parsed": [["Lovelace", "Ada", ""], ["Turing", "Alan", ""]],
        "versions": [
            {"version": "v1", "created": "Mon, 1 Jan 2024 10:00:00 GMT"},
            {"version": "v2", "created": "Tue, 2 Jan 2024 10:00:00 GMT"},
        ],
        "update_date": "2024-01-03",
        "doi": "10.1234/bulk.1",
    },
    {
        "id": "2401.00002",
        "title": "No License Here",
        "abstract": "A paper without a declared license should gate by default.",
        "categories": "math.CO",
        "license": None,
        "authors_parsed": [["Erdos", "Paul", ""]],
        "versions": [{"version": "v1", "created": "Wed, 3 Jan 2024 10:00:00 GMT"}],
        "update_date": "2024-01-03",
    },
]


def _snapshot_text(records) -> str:
    return "\n".join(json.dumps(r) for r in records) + "\n"


class _CountingFile:
    """A file-like wrapping a list of lines that COUNTS how many lines were
    read. Iterating it line-by-line is the stream proof: a fully-materializing
    reader would call read()/readlines(), which this object does not provide."""

    def __init__(self, text: str) -> None:
        self._lines = text.splitlines(keepends=True)
        self.lines_yielded = 0

    def __iter__(self):
        for line in self._lines:
            self.lines_yielded += 1
            yield line


# ---------------------------------------------------------------------------
# Bulk discovery — candidate shape + parity
# ---------------------------------------------------------------------------


def test_bulk_yields_candidates_with_export_parity(tmp_path):
    """The bulk path yields ArxivPaper candidates whose shape matches the
    export adapter: base id, version suffix, collapsed title/abstract, author
    list, category list, and the license URI as the rights anchor."""
    snap = tmp_path / "snapshot.json"
    snap.write_text(_snapshot_text(_RECORDS), encoding="utf-8")

    papers = bulk.bulk_candidates_from_path(str(snap))
    assert [p.arxiv_id for p in papers] == ["2401.00001", "2401.00002"]

    p0 = papers[0]
    assert isinstance(p0, ArxivPaper)
    assert p0.version == "v2"  # last version
    assert p0.title == "A Bulk Discovered Paper"  # whitespace collapsed
    assert p0.abstract == "We study something meaningful about systems."
    assert p0.authors == ["Ada Lovelace", "Alan Turing"]
    assert p0.categories == ["cs.LG", "cs.AI"]
    assert p0.primary_category == "cs.LG"
    # The license is the rights anchor downstream gates on — identical to the
    # export Atom <license> element.
    assert p0.license_uri == "http://creativecommons.org/licenses/by/4.0/"
    assert p0.pdf_url == "https://arxiv.org/pdf/2401.00001"
    assert p0.abs_url == "https://arxiv.org/abs/2401.00001"

    # No-license record carries license_uri=None -> deny-by-default downstream.
    assert papers[1].license_uri is None


def test_bulk_category_filter_and_limit(tmp_path):
    """category filters to records carrying that exact category; limit caps."""
    snap = tmp_path / "snapshot.json"
    snap.write_text(_snapshot_text(_RECORDS), encoding="utf-8")

    cs = bulk.bulk_candidates_from_path(str(snap), category="cs.LG")
    assert [p.arxiv_id for p in cs] == ["2401.00001"]

    capped = bulk.bulk_candidates_from_path(str(snap), limit=1)
    assert len(capped) == 1


def test_bulk_is_streamed_not_materialized():
    """iter_bulk_candidates consumes the snapshot LINE BY LINE (stream), and
    stops early at the limit without reading the rest of the file."""
    big = _snapshot_text(_RECORDS * 100)  # 200 records
    cf = _CountingFile(big)

    out = list(bulk.iter_bulk_candidates(cf, limit=3))
    assert len(out) == 3
    # It stopped early: only enough lines to yield 3 candidates were read,
    # NOT all 200. (Each record is one line here.)
    assert cf.lines_yielded == 3


def test_bulk_skips_malformed_lines_without_aborting():
    """A blank or non-JSON line in a 2.5M-line dataset is skipped, not fatal."""
    text = (
        json.dumps(_RECORDS[0]) + "\n"
        + "\n"  # blank
        + "}{ not json\n"  # garbage
        + json.dumps({"no_id": True}) + "\n"  # missing id -> skipped
        + json.dumps(_RECORDS[1]) + "\n"
    )
    out = list(bulk.iter_bulk_candidates(io.StringIO(text)))
    assert [p.arxiv_id for p in out] == ["2401.00001", "2401.00002"]


def test_bulk_path_never_calls_export_api(monkeypatch, tmp_path):
    """The export endpoint is NEVER called on the bulk path. We patch the
    export client's search/fetch_by_id + the low-level _http_get to RAISE; the
    bulk discovery must complete without tripping any of them."""
    import acquisition.arxiv.client as client_mod

    def _boom_search(**_k):
        raise AssertionError("export search() must not be called on bulk path")

    def _boom_fetch(*_a, **_k):
        raise AssertionError("export fetch_by_id() must not be called on bulk path")

    def _boom_http(*_a, **_k):
        raise AssertionError("export _http_get() must not be called on bulk path")

    monkeypatch.setattr(client_mod, "search", _boom_search)
    monkeypatch.setattr(client_mod, "fetch_by_id", _boom_fetch)
    monkeypatch.setattr(client_mod, "_http_get", _boom_http)

    snap = tmp_path / "snapshot.json"
    snap.write_text(_snapshot_text(_RECORDS), encoding="utf-8")
    papers = bulk.bulk_candidates_from_path(str(snap))
    assert len(papers) == 2  # discovery completed, no export call


# ---------------------------------------------------------------------------
# Per-PDF fetch — reuses throttle + assert_pdf
# ---------------------------------------------------------------------------


def _paper(arxiv_id="2401.00001") -> ArxivPaper:
    return bulk.record_to_paper(
        {
            "id": arxiv_id,
            "title": "t",
            "abstract": "a",
            "categories": "cs.LG",
            "versions": [{"version": "v1", "created": "Mon, 1 Jan 2024 10:00:00 GMT"}],
        }
    )


def test_fetch_bulk_pdf_returns_real_pdf(tmp_path, monkeypatch):
    """A structurally-valid PDF body (built by the in-tree text_to_pdf, so it
    passes the assert_pdf pypdf-parse layer) is returned unchanged; the host is
    not banned."""
    from acquisition.books.public_domain import text_to_pdf

    path = str(tmp_path / "throttle.json")
    throttle = SourceThrottle(state_path=path, now=lambda: 1000.0, sleep=lambda _s: None)
    arxiv_throttle = _isolated_arxiv_throttle(tmp_path, monkeypatch)

    pdf = text_to_pdf("a real arxiv paper body " * 20, title="Bulk Paper")

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=pdf, headers={"content-type": "application/pdf"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(_handler))
    out = bulk.fetch_bulk_pdf(
        _paper(), throttle=throttle, client=client, _arxiv_throttle=arxiv_throttle
    )
    client.close()
    assert out == pdf
    assert throttle.banned_until("arxiv_pdf") == 0.0  # not banned


def test_fetch_bulk_pdf_rejects_html_landing_page(tmp_path, monkeypatch):
    """An HTML landing page (b'<!DO') served where a PDF was expected is a
    counted NotAPdf, not a crash — the shared assert_pdf check rejects it."""
    path = str(tmp_path / "throttle.json")
    throttle = SourceThrottle(state_path=path, now=lambda: 1000.0, sleep=lambda _s: None)
    arxiv_throttle = _isolated_arxiv_throttle(tmp_path, monkeypatch)

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"<!DOCTYPE html><html><body>paywall</body></html>",
            headers={"content-type": "text/html"}, request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(_handler))
    with pytest.raises(NotAPdf):
        bulk.fetch_bulk_pdf(
            _paper(), throttle=throttle, client=client, _arxiv_throttle=arxiv_throttle
        )
    client.close()


def test_fetch_bulk_pdf_honors_active_ban_without_fetching(tmp_path, monkeypatch):
    """When the arxiv_pdf host is already banned, fetch_bulk_pdf raises
    SourceBanned BEFORE issuing any request (re-hitting extends the ban)."""
    path = str(tmp_path / "throttle.json")
    throttle = SourceThrottle(state_path=path, now=lambda: 1000.0, sleep=lambda _s: None)
    throttle.note_response("arxiv_pdf", 429)  # ban the PDF host
    arxiv_throttle = _isolated_arxiv_throttle(tmp_path, monkeypatch)

    def _handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch while banned")

    client = httpx.Client(transport=httpx.MockTransport(_handler))
    with pytest.raises(SourceBanned):
        bulk.fetch_bulk_pdf(
            _paper(), throttle=throttle, client=client, _arxiv_throttle=arxiv_throttle
        )
    client.close()


def test_fetch_bulk_pdf_429_arms_sentinel(tmp_path, monkeypatch):
    """A 429 from the PDF host arms the arxiv_pdf ban sentinel (so a re-run
    honors it) before the HTTPStatusError propagates."""
    path = str(tmp_path / "throttle.json")
    throttle = SourceThrottle(state_path=path, now=lambda: 1000.0, sleep=lambda _s: None)
    arxiv_throttle = _isolated_arxiv_throttle(tmp_path, monkeypatch)

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request)

    client = httpx.Client(transport=httpx.MockTransport(_handler))
    with pytest.raises(httpx.HTTPStatusError):
        bulk.fetch_bulk_pdf(
            _paper(), throttle=throttle, client=client, _arxiv_throttle=arxiv_throttle
        )
    client.close()
    assert throttle.is_banned("arxiv_pdf")
