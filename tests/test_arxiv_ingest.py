"""Tests for rights-aware arXiv ingest + CLI (SPR-02 M3 + M5).

NO live HTTP: search responses come from inline-XML MockTransport feeds,
and the PDF is injected as bytes (a tiny real PDF built via
``acquisition.books.public_domain.text_to_pdf``) so CI never touches the
network.

The asserted split is the invariant in action:
  - a CC-BY paper -> opt_in_licensed, servable_full_text True, basis names
    the license + URI;
  - a default-arXiv-terms paper -> gated, servable_full_text False.
And --dry-run writes nothing.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv import (  # noqa: E402
    ArxivPaper,
    ArxivThrottle,
    ingest_paper_with_rights,
)
from acquisition.arxiv.client import _parse_response  # noqa: E402
from acquisition.books.public_domain import text_to_pdf  # noqa: E402
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS  # noqa: E402
from tools import ingest_arxiv  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: feeds with explicit licenses + a tiny real PDF
# ---------------------------------------------------------------------------


def _feed(arxiv_id: str, license_uri: str) -> bytes:
    lic = (
        f'<arxiv:license>{license_uri}</arxiv:license>' if license_uri else ""
    )
    return (
        f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/{arxiv_id}v1</id>
    <updated>2024-02-15T12:00:00Z</updated>
    <published>2024-02-05T09:15:33Z</published>
    <title>Paper {arxiv_id}</title>
    <summary>Abstract for {arxiv_id}.</summary>
    <author><name>Jane Doe</name></author>
    <arxiv:primary_category term="cs.AI"/>
    {lic}
  </entry>
</feed>
"""
    ).encode("utf-8")


_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"


def _paper(arxiv_id: str, license_uri: str) -> ArxivPaper:
    return _parse_response(_feed(arxiv_id, license_uri))[0]


# A tiny PDF with enough words to clear MIN_INGEST_WORD_COUNT (100). The
# adapter reads + chunks this; we never hit the network.
_PDF_TEXT = (
    "This is a synthetic academic paper body used as ingest test fixture. "
    * 40
)
_PDF_BYTES = text_to_pdf(_PDF_TEXT, title="Test Paper")


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


@pytest.fixture
def temp_db_and_events(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-arxiv-ingest-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


# ---------------------------------------------------------------------------
# M3: rights-aware ingest split (injected PDF bytes)
# ---------------------------------------------------------------------------


def test_cc_by_paper_ingests_servable(temp_db_and_events):
    paper = _paper("2402.00001", _CC_BY)
    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    assert res.content_class == "opt_in_licensed"
    assert res.redistributable is True
    assert res.servable_full_text is True
    # Basis names the license + URI for the audit trail.
    assert "CC BY" in res.license_basis
    assert "creativecommons.org/licenses/by/4.0" in res.license_basis


def test_default_terms_paper_ingests_gated(temp_db_and_events):
    paper = _paper("2402.00002", _ARXIV_DEFAULT)
    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    assert res.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert res.redistributable is False
    assert res.servable_full_text is False
    assert res.license_basis.startswith("GATED")


def test_missing_license_paper_ingests_gated(temp_db_and_events):
    """Deny-by-default through the full ingest path: no license -> gated."""
    paper = _paper("2402.00003", "")
    assert paper.license_uri is None
    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    assert res.servable_full_text is False
    assert res.content_class == GATED_DEFAULT_CONTENT_CLASS


def test_ingest_persists_basis_in_substrate(temp_db_and_events):
    """The license_basis must land on the book_assets row — assert via a
    direct substrate query, not just the return value."""
    import duckdb

    paper = _paper("2402.00004", _CC_BY)
    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    con = duckdb.connect(temp_db_and_events["db_path"])
    try:
        row = con.execute(
            "SELECT license_basis FROM book_assets WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
        (content_class,) = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert "creativecommons.org/licenses/by/4.0" in row[0]
    assert content_class == "opt_in_licensed"


def test_empty_pdf_raises(temp_db_and_events):
    paper = _paper("2402.00005", _CC_BY)
    with pytest.raises(ValueError, match="empty PDF"):
        ingest_paper_with_rights(
            paper,
            investigation_id="inv-test",
            pdf_bytes=b"",
            db_path=temp_db_and_events["db_path"],
            embedder=_StubEmbedder(),
        )


def test_injected_fetch_callable_is_used(temp_db_and_events):
    """When pdf_bytes is omitted, the injected fetch_pdf is called with the
    arxiv id (proves the fetch is injectable; CI never hits the network)."""
    seen = {}

    def fake_fetch(arxiv_id: str) -> bytes:
        seen["id"] = arxiv_id
        return _PDF_BYTES

    paper = _paper("2402.00006", _CC_BY)
    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        fetch_pdf=fake_fetch,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    assert seen["id"] == "2402.00006"
    assert res.servable_full_text is True


# ---------------------------------------------------------------------------
# M5: CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_writes_nothing(temp_db_and_events, capsys, monkeypatch):
    """--dry-run reports the rights decision per paper and writes NO rows."""
    feed = _feed("2402.10001", _CC_BY)

    # Patch the client's HTTP layer so search() returns our feed offline,
    # and neutralise the throttle's real state file.
    monkeypatch.setattr(
        "acquisition.arxiv.client._http_get",
        lambda url, client=None: feed,
    )
    monkeypatch.setenv(
        "ANTIEK_ARXIV_THROTTLE_PATH",
        os.path.join(temp_db_and_events["tmpdir"], "throttle.json"),
    )

    rc = ingest_arxiv.main(["--query", "anything", "--limit", "1", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "SERVABLE" in out
    assert "2402.10001" in out

    # The db file was never created (dry-run does not open the substrate).
    assert not os.path.exists(temp_db_and_events["db_path"])


def test_cli_real_run_splits_servable_and_gated(
    temp_db_and_events, monkeypatch
):
    """A real (offline) run ingests a CC-BY paper as servable and a
    default-terms paper as gated. Search + per-id fetch are mocked; the PDF
    fetch is injected via the adapter's default replaced with fixture bytes."""
    import duckdb

    feeds = {
        "2402.20001": _feed("2402.20001", _CC_BY),
        "2402.20002": _feed("2402.20002", _ARXIV_DEFAULT),
    }

    def fake_fetch_by_id(arxiv_id, *, client=None, base_url=None):
        return _parse_response(feeds[arxiv_id])[0]

    monkeypatch.setattr(ingest_arxiv, "fetch_by_id", fake_fetch_by_id)
    # Replace the network PDF fetcher with fixture bytes. Each paper gets
    # DISTINCT bytes so book_doc_id (a content hash) doesn't collide the two
    # docs onto one row — in prod the real PDFs differ; here we force it.
    per_id_pdf = {
        "2402.20001": text_to_pdf(_PDF_TEXT + " alpha", title="A"),
        "2402.20002": text_to_pdf(_PDF_TEXT + " beta", title="B"),
    }
    monkeypatch.setattr(
        "acquisition.arxiv.adapter._default_fetch_pdf",
        lambda arxiv_id: per_id_pdf[arxiv_id],
    )
    monkeypatch.setenv(
        "ANTIEK_ARXIV_THROTTLE_PATH",
        os.path.join(temp_db_and_events["tmpdir"], "throttle.json"),
    )
    # --db-path must differ from default_db_path() or the prod guard fires.
    # The fixture sets ANTIEK_DUCKDB_PATH (the default source), so write to a
    # DISTINCT file here to prove the guard lets a genuine local path through.
    cli_db = os.path.join(temp_db_and_events["tmpdir"], "cli.duckdb")

    rc = ingest_arxiv.main(
        [
            "--ids", "2402.20001,2402.20002",
            "--db-path", cli_db,
        ]
    )
    assert rc == 0

    con = duckdb.connect(cli_db)
    try:
        rows = con.execute(
            "SELECT document_id, content_class FROM documents ORDER BY document_id"
        ).fetchall()
    finally:
        con.close()
    classes = sorted(r[1] for r in rows)
    assert "opt_in_licensed" in classes
    assert GATED_DEFAULT_CONTENT_CLASS in classes


def test_cli_rejects_prod_db(monkeypatch, capsys):
    """The prod-DB guard rejects the substrate default path (mechanical
    'never write to prod')."""
    from substrate.graph import default_db_path

    rc = ingest_arxiv.main(
        ["--ids", "2402.30001", "--db-path", default_db_path()]
    )
    assert rc == 2
    assert "prod" in capsys.readouterr().err.lower()


def test_cli_requires_selection(capsys):
    rc = ingest_arxiv.main([])
    assert rc == 2
    assert "choose" in capsys.readouterr().err.lower()


def test_cli_requires_db_path_for_real_run(capsys):
    rc = ingest_arxiv.main(["--ids", "2402.40001"])
    assert rc == 2
    assert "db-path" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# DEFECT 1: a LIVE 429 sets the ban sentinel + halts the batch (end-to-end)
# ---------------------------------------------------------------------------


def test_live_429_pdf_fetch_sets_sentinel_and_halts_batch(
    temp_db_and_events, monkeypatch
):
    """Drive the REAL run_batch path with a PDF fetch that returns HTTP 429
    (as the production fetcher would: raise_for_status -> HTTPStatusError).

    This exercises note_response INDIRECTLY — the CLI must catch the live
    HTTP error and feed its status to the throttle. Asserts (i) the
    banned_until sentinel is actually written to the throttle's state file,
    and (ii) the batch backs off after the 429 instead of marching through
    every paper. Against the unwired code (no note_response call at the CLI
    boundary) BOTH assertions fail: nothing persists the sentinel and the
    generic except-Exception keeps the batch going.
    """
    state_path = os.path.join(temp_db_and_events["tmpdir"], "throttle.json")
    throttle = ArxivThrottle(
        state_path=state_path,
        min_spacing_s=0.0,  # don't actually sleep between papers
    )

    papers = [
        _paper("2402.50001", _CC_BY),
        _paper("2402.50002", _CC_BY),
        _paper("2402.50003", _CC_BY),
    ]

    attempted: list[str] = []

    def fetch_429(arxiv_id: str) -> bytes:
        attempted.append(arxiv_id)
        url = f"https://arxiv.org/pdf/{arxiv_id}"
        request = httpx.Request("GET", url)
        response = httpx.Response(429, request=request, headers={})
        response.raise_for_status()  # raises httpx.HTTPStatusError, as in prod
        return b""

    monkeypatch.setattr(
        "acquisition.arxiv.adapter._default_fetch_pdf", fetch_429
    )

    report = ingest_arxiv.run_batch(
        papers,
        investigation_id="inv-test",
        db_path=temp_db_and_events["db_path"],
        throttle=throttle,
    )

    # (i) the sentinel is on disk and active.
    assert os.path.exists(state_path)
    persisted = json.loads(open(state_path, encoding="utf-8").read())
    assert persisted["banned_until"] > 0.0
    assert throttle.is_banned() is True

    # (ii) the batch backed off — it did NOT attempt every paper.
    assert len(attempted) < len(papers)
    assert report.candidates == len(papers)
