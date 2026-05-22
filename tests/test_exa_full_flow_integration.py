"""End-to-end integration test for Exa & Browserbase spec §6.10.

Spec text:
    "Integration test: one synthetic Exa response (via httpx.MockTransport)
    flows through discover → ingest_url → graph writes, with all events
    emitted in order, and idempotent re-run produces no duplicate graph
    rows."

Prior gap-closure tests cover the pieces separately:
  - tests/test_acquisition_search_exa.py — discover() side
  - tests/test_acquisition_search_exa_cache.py — cache layer
  - tests/test_spec_gaps.py — url_alias short-circuit via ingest_url directly
  - tests/test_spec_deviations.py — discover with same URL across queries

This module composes them into one test that exercises the REAL
ingest_url path (not a mock) against a tmp DuckDB and verifies the
spec's exact acceptance pattern.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import duckdb
import httpx
import pytest


@pytest.fixture
def full_flow_env(tmp_path, monkeypatch):
    """Isolated environment for the full discover→promote→ingest flow.

    Wires every external seam to a deterministic, in-process stub:
      - ANTIEK_HOME → tmp_path (budgets, discovery_events)
      - ANTIEK_DUCKDB_PATH → tmp_path/graph.duckdb
      - ANTIEK_RESEARCH_EVENTS_DIR → tmp_path/substrate_events
      - ANTIEK_LEGAL_GATE_DISABLED=1 (real gate has empty registry
        anyway, but disabling keeps the test deterministic regardless
        of future registry edits)
      - EXA_API_KEY → "test-key" (mocked, never hits network)
    """
    substrate_events = tmp_path / "substrate_events"
    substrate_events.mkdir()
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(substrate_events))
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_DISABLED", "1")

    # Initialize the graph schema so the substrate's ingest_url has
    # tables to write to.
    from substrate.graph import ensure_initialized
    ensure_initialized(str(tmp_path / "graph.duckdb"))

    yield {
        "tmp": tmp_path,
        "db": str(tmp_path / "graph.duckdb"),
        "substrate_events": substrate_events,
        "discovery_events": tmp_path / "discovery_events",
    }


class _StubEmbedder:
    """Deterministic float vector — substitute for sentence-transformers
    so the test doesn't pull the model weights."""

    def encode(self, text: str):
        return [0.0, 0.0, 0.0, 0.0]


def _count(db: str, table: str, where: str = "") -> int:
    con = duckdb.connect(db, read_only=True)
    try:
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def _read_action_types(events_dir: Path) -> List[str]:
    """Read every JSONL file in events_dir; return action_types in
    emit order."""
    out: List[str] = []
    for f in sorted(events_dir.rglob("*.jsonl")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            out.append(ev.get("action_type", ""))
    return out


def test_spec_6_10_full_flow_discover_promote_ingest_idempotent(
    full_flow_env, monkeypatch
):
    """Closes Finding D from the 2026-05-22 third-pass audit.

    Spec §6.10 acceptance criterion:
      1. discover() returns ≥1 result against a synthetic Exa response.
      2. Each result emits exactly one DiscoveryProposedPayload.
      3. Promoting a result via ingest_url emits exactly one
         DiscoverySelectedPayload{decision="ingested"} with non-null
         document_id matching url_doc_id(final_url).
      4. Integration: discover → ingest_url → graph writes in order.
      5. Idempotent re-run produces no duplicate graph rows.
    """
    from acquisition.search.exa import ExaClient, discover, promote_discovery
    from acquisition.urls.adapter import url_doc_id
    import acquisition.urls.adapter as urls_adapter_mod

    # ── Step 1: synthetic Exa response via MockTransport ──────────
    target_url = "https://example.com/the-article"

    def exa_handler(request):
        return httpx.Response(200, json={
            "results": [{
                "url": target_url,
                "title": "The Article",
                "score": 0.92,
                "id": "exa-resp-r1",
                "text": "Snippet preview of the article body...",
            }],
            "requestId": "exa-req-integration-1",
        })

    exa_client = ExaClient(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(exa_handler)),
        sleep=lambda _s: None,
    )

    # Synthetic URL fetch returning real-ish HTML so the chunker has
    # something to work with. Monkeypatch the URL adapter's fetch()
    # rather than passing http_client through (promote_discovery
    # doesn't expose http_client today).
    def stub_url_fetch(url, *, client=None):
        from acquisition.urls.client import FetchedHtml
        # Generate ~200 words of HTML so word_count clears MIN_INGEST_WORD_COUNT.
        body = b"<html><body><h1>The Article</h1><p>" + (
            b"This is the article body. " * 100
        ) + b"</p></body></html>"
        return FetchedHtml(
            requested_url=url, final_url=url, status_code=200,
            content_type="text/html; charset=utf-8", charset="utf-8",
            body=body,
        )

    monkeypatch.setattr(urls_adapter_mod, "fetch", stub_url_fetch)

    # ── Step 2: discover ─────────────────────────────────────────
    proposals = discover(
        query="claude pricing late 2025",
        investigation_id="inv-integration-1",
        num_results=1,
        client=exa_client,
        use_cache=False,
    )
    assert len(proposals) == 1, "exactly one proposal from one Exa result"
    proposal = proposals[0]
    assert proposal.url == target_url
    assert proposal.proposed_event_id is not None  # event was emitted

    # ── Step 3: pre-promote state — no documents yet ─────────────
    db = full_flow_env["db"]
    assert _count(db, "documents") == 0
    assert _count(db, "chunks") == 0
    assert _count(db, "url_alias") == 0

    # ── Step 4: promote (calls REAL ingest_url against REAL DuckDB) ──
    result1 = promote_discovery(
        proposal,
        investigation_id="inv-integration-1",
        db_path=db,
        embedder=_StubEmbedder(),
    )
    assert result1.decision == "ingested"
    assert result1.document_id == url_doc_id(target_url)
    assert result1.chunks_written > 0  # chunker ran

    # ── Step 5: post-promote graph rows present ──────────────────
    docs_after_first = _count(db, "documents")
    chunks_after_first = _count(db, "chunks")
    aliases_after_first = _count(db, "url_alias")
    assert docs_after_first == 1
    assert chunks_after_first >= 1
    # url_alias rows: 1 for requested_url, 1 for final_url (same URL
    # here, so deduped to 1 — the adapter uses a set when iterating).
    assert aliases_after_first == 1

    # ── Step 6: event order ─────────────────────────────────────
    # Discovery events land in discovery_events_dir per spec §14.1.
    # Substrate events (document.loaded) land in ANTIEK_RESEARCH_EVENTS_DIR.
    disc_action_types = _read_action_types(full_flow_env["discovery_events"])
    substrate_action_types = _read_action_types(full_flow_env["substrate_events"])

    # Discovery side: proposed → selected (in this order).
    assert disc_action_types == [
        "discovery.proposed", "discovery.selected",
    ], f"discovery events not in order: {disc_action_types}"

    # Substrate side: document.loaded (from ingest_url).
    assert "document.loaded" in substrate_action_types

    # ── Step 7: idempotent re-run ────────────────────────────────
    # Re-promote the SAME proposal. The url_alias short-circuit from
    # Gap 6 should fire → ingest_url returns
    # skipped_reason="alias_resolved_to_existing_document" → no new
    # document/chunk rows.
    result2 = promote_discovery(
        proposal,
        investigation_id="inv-integration-1",
        db_path=db,
        embedder=_StubEmbedder(),
    )
    assert result2.decision == "ingested"
    assert result2.document_id == result1.document_id

    docs_after_second = _count(db, "documents")
    chunks_after_second = _count(db, "chunks")
    assert docs_after_second == docs_after_first, \
        "spec §6.10: idempotent re-run must NOT add duplicate document rows"
    assert chunks_after_second == chunks_after_first, \
        "spec §6.10: idempotent re-run must NOT add duplicate chunk rows"


def test_spec_6_10_re_promote_via_different_query_still_idempotent(
    full_flow_env, monkeypatch
):
    """A subtler variant: discover the same URL via TWO different
    queries. Per Deviation A's §6.5 closure, the two proposals get
    DIFFERENT discovery_ids — but the SAME url_doc_id, and url_alias
    short-circuits both ingest_url calls onto the same document row.

    The spec's "no duplicate graph rows" criterion holds even when
    the discovery_id differs.
    """
    from acquisition.search.exa import ExaClient, discover, promote_discovery
    from acquisition.urls.adapter import url_doc_id
    import acquisition.urls.adapter as urls_adapter_mod

    target_url = "https://example.com/cross-query-article"

    def exa_handler(request):
        return httpx.Response(200, json={
            "results": [{"url": target_url, "title": "X", "score": 0.9}],
            "requestId": "req",
        })

    def make_client():
        return ExaClient(
            api_key="test-key",
            client=httpx.Client(transport=httpx.MockTransport(exa_handler)),
            sleep=lambda _s: None,
        )

    def stub_fetch(url, *, client=None):
        from acquisition.urls.client import FetchedHtml
        body = b"<html><body>" + b"hello world " * 100 + b"</body></html>"
        return FetchedHtml(
            requested_url=url, final_url=url, status_code=200,
            content_type="text/html", charset="utf-8", body=body,
        )

    monkeypatch.setattr(urls_adapter_mod, "fetch", stub_fetch)

    db = full_flow_env["db"]

    [proposal_a] = discover(
        query="query A", investigation_id="inv-cross-q",
        num_results=1, client=make_client(), use_cache=False,
    )
    [proposal_b] = discover(
        query="query B", investigation_id="inv-cross-q",
        num_results=1, client=make_client(), use_cache=False,
    )
    # Per Deviation A: different queries → different discovery_ids
    # for the same URL within the same investigation.
    assert proposal_a.discovery_id != proposal_b.discovery_id
    assert proposal_a.url == proposal_b.url == target_url

    # Promote A — ingests the document.
    result_a = promote_discovery(
        proposal_a, investigation_id="inv-cross-q",
        db_path=db, embedder=_StubEmbedder(),
    )
    assert result_a.decision == "ingested"
    docs_after_a = _count(db, "documents")
    chunks_after_a = _count(db, "chunks")

    # Promote B — should short-circuit via url_alias and NOT create
    # duplicate rows.
    result_b = promote_discovery(
        proposal_b, investigation_id="inv-cross-q",
        db_path=db, embedder=_StubEmbedder(),
    )
    assert result_b.decision == "ingested"
    assert result_b.document_id == result_a.document_id == url_doc_id(target_url)

    docs_after_b = _count(db, "documents")
    chunks_after_b = _count(db, "chunks")
    assert docs_after_b == docs_after_a, \
        "cross-query re-promote of same URL must not duplicate documents"
    assert chunks_after_b == chunks_after_a, \
        "cross-query re-promote of same URL must not duplicate chunks"
