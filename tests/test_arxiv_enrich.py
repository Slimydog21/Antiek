"""Tests for arXiv → OpenAlex enrichment (SPR-03 M1 + M2).

NO live HTTP: the OpenAlex fetch goes through the existing connector's
``fetch_work_record``, exercised against a RECORDED ``/works`` response
(trimmed to load-bearing fields, but INCLUDING the ``authorships`` /
``author.orcid`` / ``author_position`` / ``referenced_works`` /
``cited_by_count`` the rights-router fixtures omit). The HTTP path uses
``httpx.MockTransport`` + a no-sleep ``OAThrottle``, the house pattern.

The DB-touching path uses a temp DuckDB seeded with a real SPR-01 OAI row via
``persist_oai_records`` (so the enrichment merges onto a genuinely-shaped
metadata blob, not a hand-built one).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

import duckdb
import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.adapter import arxiv_doc_id  # noqa: E402
from acquisition.arxiv.authors import parse_authorships  # noqa: E402
from acquisition.arxiv.enrich_openalex import (  # noqa: E402
    build_enrichment,
    enrich_corpus,
    merge_enrichment,
    render_coverage_report,
)
from acquisition.arxiv.oai_persist import persist_oai_records  # noqa: E402
from acquisition.openaccess.openalex import (  # noqa: E402
    arxiv_doi,
    fetch_work_record,
)
from acquisition.openaccess.throttle import OAThrottle  # noqa: E402
from substrate.schemas.documents import ArxivOaiRecord, EnrichedAuthor  # noqa: E402


# A throttle that never actually sleeps — deterministic + fast in CI.
def _no_sleep_throttle() -> OAThrottle:
    return OAThrottle(min_spacing_s=0.0, sleep=lambda _s: None)


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


# ---------------------------------------------------------------------------
# Recorded OpenAlex /works response — INCLUDING the fields the rights-router
# fixtures discard: authorships (with author.orcid + author_position),
# referenced_works, cited_by_count.
# ---------------------------------------------------------------------------

_ARXIV_ID = "2402.03300"

_OPENALEX_ENRICHED_WORK = {
    "id": "https://openalex.org/W4392000001",
    "doi": "https://doi.org/10.48550/arxiv.2402.03300",
    "title": "Sample Paper About Decomposition",
    "cited_by_count": 42,
    "open_access": {"is_oa": True, "oa_status": "green"},
    "best_oa_location": {"is_oa": True, "license": "cc-by"},
    "authorships": [
        {
            "author_position": "first",
            "raw_author_name": "Jane Doe",
            "author": {
                "id": "https://openalex.org/A111",
                "display_name": "Jane Doe",
                "orcid": "https://orcid.org/0000-0002-1825-0097",
            },
        },
        {
            "author_position": "middle",
            "raw_author_name": "John Smith",
            "author": {
                "id": "https://openalex.org/A222",
                "display_name": "John Smith",
                # No ORCID — must store None, never invented.
                "orcid": None,
            },
        },
        {
            "author_position": "last",
            "raw_author_name": "Ada Lovelace",
            "author": {
                "id": "https://openalex.org/A333",
                "display_name": "Ada Lovelace",
                "orcid": "https://orcid.org/0000-0001-2345-6789",
            },
        },
    ],
    "referenced_works": [
        "https://openalex.org/W1000",
        "https://openalex.org/W2000",
    ],
}

_OPENALEX_EMPTY = {"results": []}
_OPENALEX_ONE = {"results": [_OPENALEX_ENRICHED_WORK]}


@pytest.fixture
def temp_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-arxiv-enrich-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "tmpdir": tmpdir}


def _seed_arxiv_row(db_path: str, *, arxiv_id: str = _ARXIV_ID, license_uri=None):
    """Land one SPR-01-shaped arXiv OAI row so enrichment merges onto a real blob."""
    rec = ArxivOaiRecord(
        arxiv_id=arxiv_id,
        datestamp="2024-02-05",
        license_uri=license_uri,
        title="Sample Paper About Decomposition",
        categories=("cs.AI", "cs.LG"),
    )
    persist_oai_records([rec], db_path=db_path)


def _read_metadata(db_path: str, document_id: str) -> dict:
    con = duckdb.connect(db_path)
    try:
        (raw,) = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?", [document_id]
        ).fetchone()
    finally:
        con.close()
    return json.loads(raw) if isinstance(raw, str) else raw


# ---------------------------------------------------------------------------
# Connector helper: fetch_work_record (no fork — reuses _build_url/_http_get)
# ---------------------------------------------------------------------------


def test_arxiv_doi_derivation():
    assert arxiv_doi("2402.03300") == "10.48550/arXiv.2402.03300"


def test_fetch_work_record_joins_by_arxiv_id_via_doi():
    """The PRIMARY join derives the DataCite arXiv DOI and filters OpenAlex on
    it; the request carries the polite-pool mailto."""
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        return httpx.Response(200, json=_OPENALEX_ONE)

    work = fetch_work_record(
        arxiv_id=_ARXIV_ID, client=_mock_client(handler), throttle=_no_sleep_throttle()
    )
    assert work is not None
    assert work["id"] == "https://openalex.org/W4392000001"
    assert "mailto=" in seen["url"]
    # The filter is the arXiv DOI (case preserved in the derived value).
    assert "10.48550" in seen["url"] and "2402.03300" in seen["url"]


def test_fetch_work_record_no_match_returns_none():
    """0 results on every candidate -> None (never fabricate a match)."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OPENALEX_EMPTY)

    work = fetch_work_record(
        arxiv_id=_ARXIV_ID, doi="10.1/explicit",
        client=_mock_client(handler), throttle=_no_sleep_throttle(),
    )
    assert work is None


def test_fetch_work_record_falls_back_to_explicit_doi():
    """When the arXiv-id DOI misses but the explicit DOI hits, the fallback
    candidate is tried and matched."""
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        url = str(req.url)
        if "10.48550" in url:
            return httpx.Response(200, json=_OPENALEX_EMPTY)  # primary miss
        return httpx.Response(200, json=_OPENALEX_ONE)         # fallback hit

    work = fetch_work_record(
        arxiv_id=_ARXIV_ID, doi="10.1234/real",
        client=_mock_client(handler), throttle=_no_sleep_throttle(),
    )
    assert work is not None
    assert calls["n"] == 2  # both candidates attempted


def test_fetch_work_record_requires_a_key():
    with pytest.raises(ValueError, match="arxiv_id or doi"):
        fetch_work_record()


# ---------------------------------------------------------------------------
# M2: author parsing (pure)
# ---------------------------------------------------------------------------


def test_parse_authorships_preserves_order_and_orcid():
    authors = parse_authorships(_OPENALEX_ENRICHED_WORK)
    assert [a.author_position for a in authors] == [0, 1, 2]
    assert [a.display_name for a in authors] == ["Jane Doe", "John Smith", "Ada Lovelace"]
    assert authors[0].orcid == "https://orcid.org/0000-0002-1825-0097"
    assert authors[2].orcid == "https://orcid.org/0000-0001-2345-6789"
    assert all(isinstance(a, EnrichedAuthor) for a in authors)


def test_parse_authorships_missing_orcid_is_none():
    authors = parse_authorships(_OPENALEX_ENRICHED_WORK)
    # John Smith has no ORCID — stored as None, NEVER invented.
    assert authors[1].orcid is None


def test_parse_authorships_no_authorships_key():
    assert parse_authorships({"id": "x"}) == []


def test_parse_authorships_skips_malformed_entry():
    raw = {
        "authorships": [
            {"author": {"display_name": "Real", "orcid": None}},
            {"no_author_key": True},                    # skipped
            "not-a-dict",                                # skipped
            {"author": {"display_name": "Second", "orcid": None}},
        ]
    }
    authors = parse_authorships(raw)
    assert [a.display_name for a in authors] == ["Real", "Second"]
    assert [a.author_position for a in authors] == [0, 1]  # position re-densified


def test_parse_authorships_falls_back_to_raw_author_name():
    raw = {"authorships": [{"raw_author_name": "No Display", "author": {"orcid": None}}]}
    authors = parse_authorships(raw)
    assert authors[0].display_name == "No Display"


# ---------------------------------------------------------------------------
# build_enrichment / merge_enrichment (pure)
# ---------------------------------------------------------------------------


def test_build_enrichment_shape_and_provenance():
    when = datetime(2026, 5, 30, tzinfo=timezone.utc)
    e = build_enrichment(_OPENALEX_ENRICHED_WORK, fetched_at=when)
    assert e["source"] == "openalex"
    assert e["fetched_at"] == when.isoformat()
    assert e["openalex_id"] == "https://openalex.org/W4392000001"
    assert e["cited_by_count"] == 42
    assert len(e["authors"]) == 3
    assert e["authors"][0]["orcid"] == "https://orcid.org/0000-0002-1825-0097"
    assert e["referenced_works"] == [
        {"openalex_id": "https://openalex.org/W1000", "doi": None},
        {"openalex_id": "https://openalex.org/W2000", "doi": None},
    ]


def test_build_enrichment_sparse_work():
    """A matched work with no authorships / refs / cited_by still builds a valid
    (sparse) payload — it's a match, not a miss."""
    e = build_enrichment({"id": "https://openalex.org/W1"})
    assert e["authors"] == []
    assert e["referenced_works"] == []
    assert e["cited_by_count"] == 0
    assert e["openalex_id"] == "https://openalex.org/W1"


def test_merge_enrichment_is_additive():
    existing = {"source": "arxiv_oai_pmh", "license_uri": "X", "rights_tier": "T1"}
    merged = merge_enrichment(existing, {"source": "openalex"})
    assert merged["license_uri"] == "X"
    assert merged["rights_tier"] == "T1"
    assert merged["source"] == "arxiv_oai_pmh"  # NOT overwritten by enrichment.source
    assert merged["openalex_enrichment"] == {"source": "openalex"}
    # The original dict is not mutated.
    assert "openalex_enrichment" not in existing


# ---------------------------------------------------------------------------
# M1: end-to-end enrichment over a seeded corpus (no network)
# ---------------------------------------------------------------------------


def test_enrich_corpus_matches_and_merges(temp_db):
    db_path = temp_db["db_path"]
    _seed_arxiv_row(db_path, license_uri="http://creativecommons.org/licenses/by/4.0/")

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OPENALEX_ONE)

    cov = enrich_corpus(
        db_path=db_path, client=_mock_client(handler), throttle=_no_sleep_throttle(),
        fetched_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
    )
    assert cov.attempted == 1
    assert cov.matched == 1
    assert cov.coverage == 1.0

    meta = _read_metadata(db_path, arxiv_doc_id(_ARXIV_ID))
    enr = meta["openalex_enrichment"]
    assert enr["source"] == "openalex"
    assert enr["cited_by_count"] == 42
    assert len(enr["authors"]) == 3
    assert len(enr["referenced_works"]) == 2


def test_enrich_corpus_miss_leaves_row_unenriched(temp_db):
    db_path = temp_db["db_path"]
    _seed_arxiv_row(db_path)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OPENALEX_EMPTY)  # OpenAlex has no match

    cov = enrich_corpus(
        db_path=db_path, client=_mock_client(handler), throttle=_no_sleep_throttle(),
    )
    assert cov.attempted == 1
    assert cov.matched == 0
    assert cov.missed == 1
    assert cov.coverage == 0.0

    meta = _read_metadata(db_path, arxiv_doc_id(_ARXIV_ID))
    assert "openalex_enrichment" not in meta  # un-enriched, never fabricated


def test_enrich_corpus_scoped_to_explicit_ids(temp_db):
    db_path = temp_db["db_path"]
    _seed_arxiv_row(db_path, arxiv_id="2402.03300")
    _seed_arxiv_row(db_path, arxiv_id="2401.99999")

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OPENALEX_ONE)

    cov = enrich_corpus(
        arxiv_ids=["2402.03300"], db_path=db_path,
        client=_mock_client(handler), throttle=_no_sleep_throttle(),
    )
    assert cov.attempted == 1
    assert cov.matched == 1
    # The un-targeted row stays un-enriched.
    other = _read_metadata(db_path, arxiv_doc_id("2401.99999"))
    assert "openalex_enrichment" not in other


def test_enrich_corpus_partial_coverage_reported(temp_db):
    """One id matches, one misses -> 50% coverage, computed from counts."""
    db_path = temp_db["db_path"]
    _seed_arxiv_row(db_path, arxiv_id="2402.03300")
    _seed_arxiv_row(db_path, arxiv_id="2401.99999")

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "2402.03300" in url:
            return httpx.Response(200, json=_OPENALEX_ONE)
        return httpx.Response(200, json=_OPENALEX_EMPTY)

    cov = enrich_corpus(
        db_path=db_path, client=_mock_client(handler), throttle=_no_sleep_throttle(),
    )
    assert cov.attempted == 2
    assert cov.matched == 1
    assert cov.missed == 1
    assert abs(cov.coverage - 0.5) < 1e-9

    report = render_coverage_report(cov)
    assert "50.0%" in report
    assert "OpenAlex LAGS recent arXiv" in report  # the low-coverage honesty caveat


def _corrupt_metadata(db_path: str, document_id: str, *, raw_text: str) -> None:
    """Overwrite a row's ``documents.metadata`` with non-JSON text via a direct
    DuckDB connection (mirrors how ``test_enrich_rights_immutable.py`` reads the
    DB out-of-band)."""
    con = duckdb.connect(db_path)
    try:
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = ?",
            [raw_text, document_id],
        )
    finally:
        con.close()


def test_enrich_corpus_malformed_metadata_is_skipped_not_overwritten(temp_db):
    """A row whose ``metadata`` is non-JSON is counted as a malformed MISS and is
    left BYTE-IDENTICAL — never blind-overwritten. The mock client WOULD match, so
    the only reason this is a miss is the unreadable metadata (proving the skip is
    the metadata guard, not a no-match)."""
    db_path = temp_db["db_path"]
    _seed_arxiv_row(db_path)  # a genuine, well-formed SPR-01 row first
    doc_id = arxiv_doc_id(_ARXIV_ID)

    # CORRUPT the metadata to non-JSON text through a direct duckdb connection.
    corrupt = "not json{"
    _corrupt_metadata(db_path, doc_id, raw_text=corrupt)

    # A client that WOULD match — so a miss can only come from the malformed read.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OPENALEX_ONE)

    cov = enrich_corpus(
        arxiv_ids=[_ARXIV_ID],  # scope explicitly — the corpus-scan would skip a
        db_path=db_path,        # non-arxiv_oai_pmh-shaped (now-corrupt) row.
        client=_mock_client(handler),
        throttle=_no_sleep_throttle(),
    )
    assert cov.attempted == 1
    assert cov.missed == 1
    assert cov.malformed == 1
    assert cov.matched == 0
    assert cov.coverage == 0.0

    # The row's metadata was NOT overwritten — still the exact corrupt text.
    con = duckdb.connect(db_path)
    try:
        (raw,) = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?", [doc_id]
        ).fetchone()
    finally:
        con.close()
    assert raw == corrupt  # skipped, not blind-overwritten


def test_render_report_empty_corpus():
    from acquisition.arxiv.enrich_openalex import EnrichmentCoverage

    report = render_coverage_report(EnrichmentCoverage())
    assert "No arXiv rows were attempted" in report
    assert "100.0%" in report  # the attempted=0 row still renders the denominator


def test_render_report_provisional_banner():
    """A seeded/fixture pass renders the PROVISIONAL banner near the top; a live
    run (provisional_note=None) renders no banner. The banner never moves a %."""
    from acquisition.arxiv.enrich_openalex import EnrichmentCoverage

    cov = EnrichmentCoverage(attempted=5, matched=3, missed=2, malformed=0)
    note = "Seeded fixture pass, NOT the live corpus."

    seeded = render_coverage_report(cov, provisional_note=note)
    # Banner is near the top: right under the H1, before "What this measures".
    head = seeded.split("## What this measures")[0]
    assert f"> **PROVISIONAL:** {note}" in head
    assert "60.0%" in seeded  # %'s still computed from counts, banner or not

    live = render_coverage_report(cov)  # provisional_note=None
    assert "PROVISIONAL" not in live
    assert "60.0%" in live
