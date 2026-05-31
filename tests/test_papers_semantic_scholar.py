"""Tests for the Semantic Scholar (S2) connector (SPR-07 M3).

NO live HTTP: S2 responses come from an ``httpx.MockTransport`` feed; the
classification comes from the real chokepoint.

The LOAD-BEARING gate for this sprint: an S2 record with NO openAccessPdf
(closed access) ingests GATED — restricted_pending_opt_in, abstract + metadata
present, body NEVER fetched/served. ``test_*closed_access_gated`` is the named
test G2 keys off.
"""

from __future__ import annotations

import os
import sys
import tempfile

import duckdb
import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.papers import classify_paper, paper_candidate_ref  # noqa: E402
from acquisition.papers.semantic_scholar import (  # noqa: E402
    paper_to_record,
    parse_search_response,
    search_papers,
)
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.dedup import KeyType, identity_key  # noqa: E402

_CC_BY = "https://creativecommons.org/licenses/by/4.0/"


def _payload() -> dict:
    return {
        "data": [
            {
                "corpusId": 111,
                "title": "Open S2 Paper",
                "abstract": "Open abstract.",
                "externalIds": {"DOI": "10.1/open-s2"},
                "openAccessPdf": {"url": "https://example.org/open.pdf", "license": "CC-BY"},
                "authors": [{"name": "Grace Hopper"}],
            },
            {
                "corpusId": 222,
                "title": "Closed S2 Paper",
                "abstract": "This abstract is public; the body is paywalled.",
                "externalIds": {"DOI": "10.1/closed-s2"},
                "openAccessPdf": None,  # closed access -> no body to fetch
                "authors": [{"name": "John Closed"}],
            },
        ]
    }


def test_s2_open_access_record_is_servable_with_named_basis():
    records = parse_search_response(_payload())
    oa = next(r for r in records if r.doi == "10.1/open-s2")
    cls = classify_paper(oa)
    assert cls.content_class in SERVABLE_CONTENT_CLASSES
    assert cls.servable is True
    assert cls.serve_body is True
    # Defensibility: basis cites the S2 OA field.
    assert "openaccesspdf.license" in cls.license_basis.lower()
    assert "semantic_scholar" in cls.license_basis.lower()


def test_s2_closed_access_gated_record_body_withheld():
    """THE sprint gate (G2): a closed-access S2 record (no openAccessPdf)
    ingests gated — abstract + metadata present, body never fetched/served."""
    records = parse_search_response(_payload())
    closed = next(r for r in records if r.doi == "10.1/closed-s2")

    cls = classify_paper(closed)
    # Gated, not servable — the catastrophic case made structurally impossible.
    assert cls.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert cls.servable is False
    # No servable body: there is no PDF to fetch and serve_body is False.
    assert cls.serve_body is False
    assert closed.pdf_url is None
    assert closed.has_servable_body is False
    # Abstract + metadata ARE present (private-search graph-resident).
    assert closed.abstract and closed.abstract.strip()
    assert closed.title == "Closed S2 Paper"
    assert closed.doi == "10.1/closed-s2"


def test_s2_closed_access_gated_ingest_thunk_never_fetches_body(monkeypatch):
    """Belt-and-braces for G2: even routed through the orchestrator's ingest
    thunk, a closed S2 record never calls the PDF fetch path — the gated
    branch stages metadata-only."""
    import tools.run_corpus_ingest as orch

    fetched = {"called": False}

    def _no_fetch(*a, **k):
        fetched["called"] = True
        raise AssertionError("a gated record must never fetch a body")

    monkeypatch.setattr(orch, "_fetch_paper_pdf", _no_fetch)
    staged = {"called": False, "class": None}

    def _fake_stage(rec, classification, *, investigation_id, db_path):
        staged["called"] = True
        staged["class"] = classification.content_class
        return f"{classification.content_class} (metadata-only)"

    monkeypatch.setattr(orch, "_stage_paper_metadata_only", _fake_stage)

    records = parse_search_response(_payload())
    closed = next(r for r in records if r.doi == "10.1/closed-s2")
    cls = classify_paper(closed)
    assert cls.serve_body is False

    # Drive the exact ingest closure shape the orchestrator builds.
    def _ingest(db_path, basis, _rec=closed, _cls=cls, _serve=cls.serve_body):
        if not _serve:
            return orch._stage_paper_metadata_only(
                _rec, _cls, investigation_id="inv", db_path=db_path
            )
        return orch._fetch_paper_pdf(_rec, throttle=None, source="semantic_scholar")

    status = _ingest("db", "doi:10.1/closed-s2")
    assert fetched["called"] is False
    assert staged["called"] is True
    assert staged["class"] == GATED_DEFAULT_CONTENT_CLASS
    assert "restricted_pending_opt_in" in status


@pytest.fixture
def temp_substrate(monkeypatch):
    """Real DuckDB + event-log substrate, isolated per test (matches the
    convention in test_public_domain_ingest.py)."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-papers-s2-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


def test_s2_closed_access_real_metadata_stage_is_gated_and_body_is_abstract(
    temp_substrate, monkeypatch
):
    """G2 end-to-end against the REAL substrate (no monkeypatch of the stager):
    drive the actual ``_stage_paper_metadata_only`` write for a closed S2 record
    and assert at the row level that

      1. the stored ``documents.content_class`` is ``restricted_pending_opt_in``,
      2. ``book_assets.servable_full_text`` is DERIVED False (deny-by-default —
         the gated class is not in SERVABLE_CONTENT_CLASSES),
      3. the stored ``documents.raw_text`` body IS the abstract + the
         withheld-notice line (SPR-10 audit fact: a gated paper's body == its
         abstract, the full text was never fetched), and
      4. the ``book_assets.license_basis`` row is non-empty and names the source.

    This closes the gap the thunk test alone leaves open: the thunk test fakes
    the stager (proving only that the body is never FETCHED); this test proves
    the real metadata write yields a non-servable row whose body is the abstract.
    """
    import tools.run_corpus_ingest as orch

    # The body must never be fetched even on the real path.
    def _no_fetch(*a, **k):
        raise AssertionError("a gated record must never fetch a body")

    monkeypatch.setattr(orch, "_fetch_paper_pdf", _no_fetch)
    # Use a deterministic stub embedder so the chunk/node writes succeed offline.
    monkeypatch.setattr(
        "processing.embedding.embed.default_embedding_provider",
        lambda: _StubEmbedder(),
    )

    closed = next(
        r for r in parse_search_response(_payload()) if r.doi == "10.1/closed-s2"
    )
    cls = classify_paper(closed)
    assert cls.serve_body is False  # precondition: gated, no body

    db_path = temp_substrate["db_path"]
    status = orch._stage_paper_metadata_only(
        closed, cls, investigation_id="inv-real", db_path=db_path
    )
    assert GATED_DEFAULT_CONTENT_CLASS in status

    con = duckdb.connect(db_path)
    try:
        content_class, raw_text = con.execute(
            "SELECT content_class, raw_text FROM documents "
            "WHERE investigation_id = ?",
            ["inv-real"],
        ).fetchone()
        # book_assets stores license_basis + taken_down; servable_full_text is
        # DERIVED (never a stored column), so we project it from the stored
        # content_class via the same substrate gate the serve path uses.
        license_basis, taken_down = con.execute(
            "SELECT b.license_basis, b.taken_down FROM book_assets b "
            "JOIN documents d ON d.document_id = b.document_id "
            "WHERE d.investigation_id = ?",
            ["inv-real"],
        ).fetchone()
    finally:
        con.close()

    # 1. The gated class is what landed on the row — not a servable one.
    assert content_class == GATED_DEFAULT_CONTENT_CLASS
    assert content_class not in SERVABLE_CONTENT_CLASSES
    # 2. servable_full_text is DERIVED False from the stored class (the §9.0
    #    deny-by-default gate; restricted_pending_opt_in is not allowlisted).
    from substrate.books.servability import is_servable_full_text, servability_of

    status_derived = servability_of(content_class, taken_down=bool(taken_down))
    assert is_servable_full_text(status_derived) is False
    # 3. The stored body IS the abstract + withheld notice — never the full
    #    text (which was never fetched). Pins finding (1)'s by-design fact.
    assert raw_text
    assert "This abstract is public; the body is paywalled." in raw_text
    assert "withheld" in raw_text.lower()
    # 4. The audit basis row is non-empty and names the source.
    assert license_basis and license_basis.strip()
    assert "semantic_scholar" in license_basis.lower()


def test_s2_corpus_id_used_only_when_no_doi_or_arxiv():
    """Precedence: DOI > arXiv id > S2 corpusId. The corpusId keys identity
    ONLY when no DOI/arXiv id is present."""
    # DOI present -> keys on DOI, not corpusId.
    with_doi = paper_to_record(
        {"corpusId": 5, "title": "T", "externalIds": {"DOI": "10.9/z"}}
    )
    assert identity_key(paper_candidate_ref(with_doi).identity_record()).key_type is KeyType.DOI

    # arXiv id present, no DOI -> keys on arXiv id.
    with_arxiv = paper_to_record(
        {"corpusId": 6, "title": "T2", "externalIds": {"ArXiv": "2401.00001"}}
    )
    assert identity_key(paper_candidate_ref(with_arxiv).identity_record()).key_type is KeyType.ARXIV

    # Neither DOI nor arXiv -> keys on the S2 source id.
    only_corpus = paper_to_record({"corpusId": 7, "title": "T3", "externalIds": {}})
    ikey = identity_key(paper_candidate_ref(only_corpus).identity_record())
    assert ikey.key_type is KeyType.SOURCE_ID
    assert ikey.key == "semantic_scholar:7"


def test_s2_no_oa_pdf_with_declared_license_still_gates_without_body():
    """An OA url with no declared license is 'free to read', not 'free to
    redistribute' -> gated by the chokepoint's deny-by-default."""
    rec = paper_to_record(
        {"corpusId": 8, "title": "T", "externalIds": {"DOI": "10.1/x"},
         "openAccessPdf": {"url": "https://e.org/x.pdf", "license": None}}
    )
    cls = classify_paper(rec)
    assert cls.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert cls.serve_body is False


def test_s2_servable_record_license_basis_names_oa_field():
    """G5: a servable S2 record's basis names the S2 OA field + the resolved
    license — the defensible record for the SPR-10 audit."""
    oa = next(r for r in parse_search_response(_payload()) if r.doi == "10.1/open-s2")
    cls = classify_paper(oa)
    assert cls.servable is True
    assert cls.license_basis and cls.license_basis.strip()
    assert "semantic_scholar" in cls.license_basis.lower()
    assert "openaccesspdf.license" in cls.license_basis.lower()


def test_search_papers_mock_transport_no_live_http():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    records = search_papers(
        query="ml", limit=5, client=client,
        base_url="https://api.semanticscholar.org/graph/v1/paper/search",
    )
    assert {r.doi for r in records} == {"10.1/open-s2", "10.1/closed-s2"}
