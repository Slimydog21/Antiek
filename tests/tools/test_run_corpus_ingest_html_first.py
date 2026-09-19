"""Red-proofs that the arXiv BULK candidate path in ``tools/run_corpus_ingest.py``
actually reaches the HTML leg.

The trap this guards. ``ingest_paper_with_rights`` is HTML-first by default, but
that default is inert for a caller that hands the body in. The bulk thunk used to
pre-fetch ``pdf_bytes = fetch_bulk_pdf(...)`` and pass the bytes, which meant an
in-hand body, an arXiv request spent on it, and a PDF-quality gate that could
reject the paper before the higher-fidelity HTML rendering was ever attempted.
Flipping the adapter default alone would not have moved this call site; the
pre-fetch had to become a lazy ``fetch_pdf`` callable.

No network: the HTML fetcher is stubbed and the PDF fetcher is a tripwire.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv import adapter as _adapter  # noqa: E402
from acquisition.arxiv.html_fetch import FetchedHtml  # noqa: E402
from tools import run_corpus_ingest  # noqa: E402

_SNAPSHOT_RECORD = {
    "id": "2401.00001",
    "title": "A Bulk Discovered Paper",
    "abstract": "We study something meaningful about systems.",
    "categories": "cs.LG cs.AI",
    "license": "http://creativecommons.org/licenses/by/4.0/",
    "authors_parsed": [["Lovelace", "Ada", ""]],
    "versions": [{"version": "v1", "created": "Mon, 1 Jan 2024 10:00:00 GMT"}],
    "update_date": "2024-01-03",
}

_HTML_BODY = """\
<html><body><article class="ltx_document">
<h1 class="ltx_title">A Bulk Discovered Paper</h1>
<p class="ltx_p">The HTML rendering carries the full body text, the math and the
tables that PDF extraction flattens or drops. This fixture is long enough to
clear the stub/absent-rendering floor in html_fetch, which rejects a short body
as "arXiv has no rendering for this paper" rather than ingesting a husk.</p>
<p class="ltx_p">A second paragraph, so the chunker has something to chunk and
the word count is unambiguous.</p>
</article></body></html>
"""


@pytest.fixture
def snapshot(tmp_path):
    p = tmp_path / "arxiv-metadata-oai-snapshot.json"
    p.write_text(json.dumps(_SNAPSHOT_RECORD) + "\n", encoding="utf-8")
    return str(p)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "graph.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", str(events))
    return db_path


class _StubEmbedder:
    dimension = 16

    def encode(self, text: str) -> list[float]:
        v = [0.0] * 16
        v[abs(hash(text)) % 16] = 1.0
        return v


def _fetched(arxiv_id: str) -> FetchedHtml:
    import hashlib

    body = _HTML_BODY.encode("utf-8")
    return FetchedHtml(
        arxiv_id=arxiv_id,
        source_url=f"https://arxiv.org/html/{arxiv_id}",
        html=_HTML_BODY,
        sha256=hashlib.sha256(body).hexdigest(),
        byte_size=len(body),
        char_count=len(_HTML_BODY),
    )


def test_bulk_ingest_thunk_takes_the_html_leg_and_never_fetches_the_pdf(
    snapshot, temp_db, monkeypatch
):
    """The call site named in the brief. With an HTML rendering available, the
    thunk must ingest the HTML and must NOT spend an arXiv request on the PDF.

    ``fetch_bulk_pdf`` is a tripwire: if the pre-fetch were still eager, it
    would fire before the HTML leg ran and this test would red — which is
    exactly what it did before the call site was changed."""
    html_ids: list[str] = []

    def stub_default_html(arxiv_id: str):
        html_ids.append(arxiv_id)
        return _fetched(arxiv_id)

    def tripwire_fetch_bulk_pdf(paper, **kwargs):
        raise AssertionError(
            "fetch_bulk_pdf was called although an HTML rendering was available "
            "— the PDF pre-fetch is still eager and the HTML leg is bypassed"
        )

    monkeypatch.setattr(_adapter, "_default_fetch_html", stub_default_html)
    monkeypatch.setattr(
        "acquisition.arxiv.fetch_bulk_pdf", tripwire_fetch_bulk_pdf, raising=False
    )
    monkeypatch.setattr(
        "acquisition.arxiv.bulk.fetch_bulk_pdf", tripwire_fetch_bulk_pdf, raising=False
    )
    monkeypatch.setattr(
        _adapter, "default_embedding_provider", lambda: _StubEmbedder(), raising=False
    )

    candidates = run_corpus_ingest._arxiv_bulk_candidates(
        snapshot_path=snapshot, category=None, limit=5, investigation_id="inv-test"
    )
    assert len(candidates) == 1

    verdict = candidates[0].ingest(temp_db, "basis")

    assert html_ids == ["2401.00001"]
    # CC-BY → servable, and the body that landed is the HTML one.
    assert "source_declared_open" in verdict

    import duckdb

    con = duckdb.connect(temp_db)
    try:
        row = con.execute(
            "SELECT metadata FROM documents WHERE document_id LIKE '%2401.00001%'"
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    metadata = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    assert metadata.get("html_source_url") == "https://arxiv.org/html/2401.00001"


def test_bulk_ingest_thunk_still_gates_pdf_quality_when_html_is_absent(
    snapshot, temp_db, monkeypatch
):
    """The other half: when arXiv has no HTML rendering, the lazy PDF fetch runs
    AND the extraction-quality gate still runs on the bytes it returns. Making
    the fetch lazy must not have dropped the gate."""
    gated: list[str] = []
    fetched_pdf: list[str] = []

    monkeypatch.setattr(_adapter, "_default_fetch_html", lambda _id: None)

    def fake_fetch_bulk_pdf(paper, **kwargs):
        fetched_pdf.append(paper.arxiv_id)
        return b"%PDF-1.4 fake"

    def spy_assert_quality(pdf_bytes: bytes, *, ref_id: str) -> None:
        gated.append(ref_id)
        raise ValueError("quality gate rejected this body")

    monkeypatch.setattr(
        "acquisition.arxiv.fetch_bulk_pdf", fake_fetch_bulk_pdf, raising=False
    )
    monkeypatch.setattr(
        run_corpus_ingest, "_assert_pdf_body_quality", spy_assert_quality
    )

    candidates = run_corpus_ingest._arxiv_bulk_candidates(
        snapshot_path=snapshot, category=None, limit=5, investigation_id="inv-test"
    )
    with pytest.raises(ValueError, match="quality gate"):
        candidates[0].ingest(temp_db, "basis")

    assert fetched_pdf == ["2401.00001"], "the lazy PDF fetch did not run"
    assert gated == ["arxiv:2401.00001"], "the PDF extraction-quality gate was dropped"
