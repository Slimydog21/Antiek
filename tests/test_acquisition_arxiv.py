"""Tests for acquisition/arxiv/ (Sprint 10 day 2-3).

Coverage:

A. URL construction (client._build_search_url):
   1. query-only → search_query=all:...
   2. ids short-circuit → id_list=...
   3. AND-combine of query + author + category
   4. unknown sort passes through verbatim
   5. no fields raises ValueError
   6. ANTIEK_ARXIV_BASE_URL override honored

B. Atom parsing (client._parse_response):
   7. minimal valid feed → 1 ArxivPaper
   8. zero entries → []
   9. malformed XML → ValueError
   10. entry with version suffix → version field captured
   11. multiple authors + categories
   12. primary_category populated from <arxiv:primary_category>

C. HTTP path (search / fetch_by_id with MockTransport):
   13. search() returns parsed papers
   14. fetch_by_id returns paper for known id
   15. fetch_by_id returns None when feed is empty
   16. 4xx response raises (httpx.HTTPStatusError)

D. arxiv_doc_id:
   17. simple id → doc-arxiv-<id>
   18. id with periods preserved
   19. id with weird chars sanitized to dashes
   20. empty id raises

E. End-to-end adapter (ingest_paper):
   21. emits document.loaded with sha256 content_hash
   22. inserts documents + chunks + nodes rows
   23. chunk text round-trips through DB
   24. re-ingest of same paper → idempotent on rows, second event emits
   25. nodes carry arxiv_id + chunk_id metadata
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

from acquisition.arxiv import (
    ArxivPaper,
    arxiv_doc_id,
    fetch_by_id,
    ingest_paper,
    search,
)
from acquisition.arxiv.client import _build_search_url, _parse_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FEED_ONE_ENTRY = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2402.03300v2</id>
    <updated>2024-02-15T12:00:00Z</updated>
    <published>2024-02-05T09:15:33Z</published>
    <title>Sample Paper About Decomposition</title>
    <summary>This is the abstract.
It spans multiple lines and should be collapsed.</summary>
    <author><name>Jane Doe</name></author>
    <author><name>John Smith</name></author>
    <category term="cs.AI"/>
    <category term="cs.LG"/>
    <arxiv:primary_category term="cs.AI"/>
  </entry>
</feed>
"""

_FEED_ZERO_ENTRIES = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults
    xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">0</opensearch:totalResults>
</feed>
"""


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def _paper_for_test() -> ArxivPaper:
    return _parse_response(_FEED_ONE_ENTRY)[0]


# ---------------------------------------------------------------------------
# A. URL construction
# ---------------------------------------------------------------------------


def test_url_query_only():
    url = _build_search_url(query="GRPO")
    assert "search_query=all:GRPO" in url
    assert "max_results=5" in url
    assert "sortBy=relevance" in url


def test_url_ids_short_circuit():
    url = _build_search_url(ids=["2402.03300", "2401.12345"])
    assert "id_list=2402.03300,2401.12345" in url
    assert "search_query" not in url


def test_url_and_combines_query_author_category():
    url = _build_search_url(
        query="diffusion", author="LeCun", category="cs.AI",
    )
    assert "all:diffusion" in url
    assert "au:LeCun" in url
    assert "cat:cs.AI" in url
    assert "+AND+" in url


def test_url_unknown_sort_passes_through():
    url = _build_search_url(query="x", sort="some_custom")
    assert "sortBy=some_custom" in url


def test_url_empty_fields_raises():
    with pytest.raises(ValueError, match="requires one of"):
        _build_search_url()


def test_url_base_override(monkeypatch):
    monkeypatch.setenv("ANTIEK_ARXIV_BASE_URL", "https://staging.arxiv/api")
    url = _build_search_url(query="x")
    assert url.startswith("https://staging.arxiv/api?")


# ---------------------------------------------------------------------------
# B. Atom parsing
# ---------------------------------------------------------------------------


def test_parse_minimal_feed():
    papers = _parse_response(_FEED_ONE_ENTRY)
    assert len(papers) == 1
    p = papers[0]
    assert p.arxiv_id == "2402.03300"
    assert p.version == "v2"
    assert p.title == "Sample Paper About Decomposition"
    assert p.abs_url == "https://arxiv.org/abs/2402.03300"
    assert p.pdf_url == "https://arxiv.org/pdf/2402.03300"


def test_parse_zero_entries():
    assert _parse_response(_FEED_ZERO_ENTRIES) == []


def test_parse_malformed_xml_raises():
    with pytest.raises(ValueError, match="not valid XML"):
        _parse_response(b"<<not xml>>")


def test_parse_version_captured():
    p = _parse_response(_FEED_ONE_ENTRY)[0]
    assert p.version == "v2"


def test_parse_multiple_authors_and_categories():
    p = _parse_response(_FEED_ONE_ENTRY)[0]
    assert p.authors == ["Jane Doe", "John Smith"]
    assert p.categories == ["cs.AI", "cs.LG"]


def test_parse_primary_category_populated():
    p = _parse_response(_FEED_ONE_ENTRY)[0]
    assert p.primary_category == "cs.AI"


def test_parse_collapses_summary_whitespace():
    p = _parse_response(_FEED_ONE_ENTRY)[0]
    # Multi-line abstract collapses to single-line whitespace.
    assert "\n" not in p.abstract
    assert "This is the abstract." in p.abstract
    assert "multiple lines" in p.abstract


# ---------------------------------------------------------------------------
# C. HTTP path
# ---------------------------------------------------------------------------


def test_search_returns_papers():
    def handler(req: httpx.Request) -> httpx.Response:
        assert "search_query=all" in str(req.url)
        assert "GRPO" in str(req.url)
        return httpx.Response(200, content=_FEED_ONE_ENTRY)
    papers = search(query="GRPO", client=_mock_client(handler))
    assert len(papers) == 1
    assert papers[0].arxiv_id == "2402.03300"


def test_fetch_by_id_returns_paper():
    def handler(req: httpx.Request) -> httpx.Response:
        assert "id_list=2402.03300" in str(req.url)
        return httpx.Response(200, content=_FEED_ONE_ENTRY)
    p = fetch_by_id("2402.03300", client=_mock_client(handler))
    assert p is not None
    assert p.arxiv_id == "2402.03300"


def test_fetch_by_id_returns_none_when_empty():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_FEED_ZERO_ENTRIES)
    assert fetch_by_id("9999.99999", client=_mock_client(handler)) is None


def test_search_raises_on_4xx():
    def handler(req): return httpx.Response(404, content=b"")
    with pytest.raises(httpx.HTTPStatusError):
        search(query="x", client=_mock_client(handler))


# ---------------------------------------------------------------------------
# D. arxiv_doc_id
# ---------------------------------------------------------------------------


def test_arxiv_doc_id_simple():
    assert arxiv_doc_id("2402.03300") == "doc-arxiv-2402.03300"


def test_arxiv_doc_id_preserves_periods_and_dashes():
    assert arxiv_doc_id("hep-th-9911100") == "doc-arxiv-hep-th-9911100"


def test_arxiv_doc_id_sanitizes_oddballs():
    assert arxiv_doc_id("foo/bar baz") == "doc-arxiv-foo-bar-baz"


def test_arxiv_doc_id_empty_raises():
    with pytest.raises(ValueError):
        arxiv_doc_id("")


# ---------------------------------------------------------------------------
# E. End-to-end adapter (uses a temp DB + temp events dir)
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db_and_events(monkeypatch):
    """Spin up a temp DuckDB + events dir so end-to-end ingestion
    has a writable substrate without touching the operator's real
    ANTIEK paths."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-arxiv-test-")
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


def test_ingest_emits_document_loaded(temp_db_and_events):
    paper = _paper_for_test()
    res = ingest_paper(
        paper, investigation_id="inv-test",
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    assert res.document_id == "doc-arxiv-2402.03300"
    assert res.document_loaded_event_id is not None
    assert res.document_loaded_event_id.startswith("evt-")


def test_ingest_writes_documents_chunks_nodes(temp_db_and_events):
    import duckdb

    paper = _paper_for_test()
    res = ingest_paper(
        paper, investigation_id="inv-test",
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    con = duckdb.connect(temp_db_and_events["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
        (chunk_count,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
        (node_count,) = con.execute(
            "SELECT COUNT(*) FROM nodes WHERE node_id = ANY(?)",
            [res.node_ids],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == res.chunks_written
    assert chunk_count >= 1
    assert node_count == len(res.node_ids)


def test_ingest_chunk_text_round_trip(temp_db_and_events):
    import duckdb

    paper = _paper_for_test()
    res = ingest_paper(
        paper, investigation_id="inv-test",
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    con = duckdb.connect(temp_db_and_events["db_path"])
    try:
        rows = con.execute(
            "SELECT text FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            [res.document_id],
        ).fetchall()
    finally:
        con.close()
    blob = "\n".join(r[0] for r in rows)
    assert paper.title in blob
    assert "abstract" in blob.lower()


def test_ingest_is_idempotent_on_rows(temp_db_and_events):
    import duckdb

    paper = _paper_for_test()
    r1 = ingest_paper(
        paper, investigation_id="inv-test",
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    r2 = ingest_paper(
        paper, investigation_id="inv-test",
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r1.document_id == r2.document_id
    assert r1.chunk_ids == r2.chunk_ids
    assert r1.node_ids == r2.node_ids
    # Second call emits its own event — the trajectory is append-only.
    assert r1.document_loaded_event_id != r2.document_loaded_event_id

    con = duckdb.connect(temp_db_and_events["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()
        (chunk_count,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == r1.chunks_written


def test_ingest_nodes_carry_provenance_metadata(temp_db_and_events):
    import duckdb

    paper = _paper_for_test()
    res = ingest_paper(
        paper, investigation_id="inv-test",
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    con = duckdb.connect(temp_db_and_events["db_path"])
    try:
        rows = con.execute(
            "SELECT metadata FROM nodes WHERE node_id = ANY(?)",
            [res.node_ids],
        ).fetchall()
    finally:
        con.close()
    metas = [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in rows]
    assert all(m.get("source") == "arxiv" for m in metas)
    assert all(m.get("arxiv_id") == "2402.03300" for m in metas)
    assert all("chunk_id" in m for m in metas)
