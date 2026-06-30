"""RDR SPR-07 — provenance-complete ingestion against SPR-04 cassettes.

INERT-AI caveat: persistence + edges + dedup are REAL and tested here.
Live research runs await activation SPR-03 provider keys.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest

from acquisition.urls.adapter import ingest_url, url_doc_id
from acquisition.urls.client import FetchedHtml
from interfaces.research.api.cascade_synthesizer import (
    cascade_artifact_document_id,
    persist_cascade_synthesis_artifact,
)
from orchestration.cascade_session import CascadeSession, Leaf
from processing.embedding.embed import HashEmbedding
from roles.cascade_planner import SubQuestion, approve_plan, build_plan, persist_tree
from roles.cascade_planner.persist import load_tree
from runtime.db_lock import connect_read, connect_write
from runtime.research_runner import (
    BudgetCap,
    BudgetManager,
    HostLocalRunner,
    PromotionFunnel,
    ResearchPlan,
    make_demo_loop,
)
from runtime.research_runner.provenance_ingest import (
    make_cassette_url_fetcher,
    promote_note_with_provenance,
    resolve_source_ref,
    resolve_sources_for_note,
    verify_document_readable,
)
from runtime.research_runner.real_loop import RealLoopDeps, real_research_loop
from runtime.research_runner.protocol import StepEvent
from substrate.constants import CITES_RELATION, PERSONAL_READING_CONTENT_CLASS
from substrate.dispatch.base import NormalizedUsage, RawProviderResponse
from substrate.dispatch.router import (
    DispatchConfig,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.graph.ops import (
    document_body_hash,
    find_existing_source_document,
    insert_chunk,
    insert_document,
    normalize_source_url,
)
from substrate.graph.schema import init_database
from substrate.legal_gate import LegalGateVerdict, PermissiveLegalGate
from tests.test_real_research_loop_spr04 import (
    _CassetteProvider,
    _cassette_dispatch_config,
    _deps,
    _drive,
    _exa_client_from_cassette,
    seeded_graph,
)

_WEB_URL = "https://arxiv.org/abs/2401.00001"
_WEB_HTML = (
    "<html><head><title>A Real Paper</title></head><body><article>"
    + ("Evidence about photosynthesis chloroplast light reaction. " * 20)
    + "</article></body></html>"
)


class _Dec:
    def __init__(self, subs):
        self._subs = subs

    def decompose(self, q, *, context=""):
        return [SubQuestion(question=s) for s in self._subs]


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    reset_provider_registry()
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "antiek_home"))
    monkeypatch.setenv("ANTIEK_DISCOVERY_EVENTS_DIR", str(tmp_path / "discovery_events"))
    yield
    reset_provider_registry()


def _note_event(**data) -> StepEvent:
    return StepEvent(
        investigation_id="inv-spr07",
        seq=1,
        kind="note",
        text="Synthesized insight grounded in the cited evidence.",
        data=data,
    )


# ---------------------------------------------------------------------------
# M1 — sources persisted as readable Documents (content_class NOT NULL)
# ---------------------------------------------------------------------------


def test_web_source_persisted_as_readable_document(seeded_graph, monkeypatch):
    db_path, emb = seeded_graph
    monkeypatch.setattr(
        "substrate.graph.insight_question.graph_db_path", lambda: db_path,
    )
    url_fetcher = make_cassette_url_fetcher({_WEB_URL: _WEB_HTML})
    resolved = resolve_source_ref(
        None,
        source_document_id=_WEB_URL,
        source_kind="web_url",
        chunk_id=None,
        source_url=_WEB_URL,
        investigation_id="inv-spr07",
        embedding_provider=emb,
        url_fetcher=url_fetcher,
        db_path=db_path,
    )
    assert resolved is not None
    assert resolved.ingest_skipped is None
    con = connect_read(db_path)
    try:
        assert verify_document_readable(con, resolved.document_id)
        row = con.execute(
            "SELECT content_class, structured_blocks, raw_text FROM documents "
            "WHERE document_id = ?",
            [resolved.document_id],
        ).fetchone()
        assert row is not None
        assert row[0] == PERSONAL_READING_CONTENT_CLASS
        assert row[0] is not None  # NOT NULL gate
        assert row[1] is not None  # structured SPR-02 model
        assert row[2] and len(row[2]) > 50
    finally:
        con.close()


def test_local_source_resolves_without_reingest(seeded_graph, monkeypatch):
    db_path, emb = seeded_graph
    monkeypatch.setattr(
        "substrate.graph.insight_question.graph_db_path", lambda: db_path,
    )
    con = connect_write(db_path, purpose="test")
    try:
        chunk_row = con.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = 'doc-spr04-1' "
            "ORDER BY chunk_index LIMIT 1",
        ).fetchone()
        resolved = resolve_source_ref(
            con,
            source_document_id="doc-spr04-1",
            source_kind="local_chunk",
            chunk_id=str(chunk_row[0]),
            source_url=None,
            investigation_id="inv-spr07",
            embedding_provider=emb,
            url_fetcher=None,
        )
        assert resolved is not None
        assert resolved.document_id == "doc-spr04-1"
        assert resolved.chunk_id == str(chunk_row[0])
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M2 — dedup (normalized URL + content hash)
# ---------------------------------------------------------------------------


def test_dedup_reingest_same_url_and_body(seeded_graph, monkeypatch):
    db_path, emb = seeded_graph
    monkeypatch.setattr(
        "substrate.graph.insight_question.graph_db_path", lambda: db_path,
    )
    url_fetcher = make_cassette_url_fetcher({_WEB_URL: _WEB_HTML})
    first = resolve_source_ref(
        None,
        source_document_id=_WEB_URL,
        source_kind="web_url",
        chunk_id=None,
        source_url=_WEB_URL,
        investigation_id="inv-a",
        embedding_provider=emb,
        url_fetcher=url_fetcher,
        db_path=db_path,
    )
    con = connect_read(db_path)
    try:
        before = con.execute("SELECT count(*) FROM documents").fetchone()[0]
    finally:
        con.close()
    second = resolve_source_ref(
        None,
        source_document_id=_WEB_URL,
        source_kind="web_url",
        chunk_id=None,
        source_url=_WEB_URL,
        investigation_id="inv-b",
        embedding_provider=emb,
        url_fetcher=url_fetcher,
        db_path=db_path,
    )
    con = connect_read(db_path)
    try:
        after = con.execute("SELECT count(*) FROM documents").fetchone()[0]
        assert first and second
        assert first.document_id == second.document_id
        assert before == after  # no duplicate document row
    finally:
        con.close()


def test_dedup_same_url_different_hash_does_not_merge(seeded_graph, monkeypatch):
    db_path, emb = seeded_graph
    monkeypatch.setattr(
        "substrate.graph.insight_question.graph_db_path", lambda: db_path,
    )
    html_a = _WEB_HTML
    html_b = _WEB_HTML.replace("photosynthesis", "metabolism")
    fetcher = make_cassette_url_fetcher({_WEB_URL: html_a})
    resolve_source_ref(
        None,
        source_document_id=_WEB_URL,
        source_kind="web_url",
        chunk_id=None,
        source_url=_WEB_URL,
        investigation_id="inv-a",
        embedding_provider=emb,
        url_fetcher=fetcher,
        db_path=db_path,
    )
    from acquisition.urls.extract import html_to_markdown

    md_b = html_to_markdown(html_b.encode("utf-8"), base_url=_WEB_URL)
    norm = normalize_source_url(_WEB_URL)
    con = connect_read(db_path)
    try:
        existing = find_existing_source_document(
            con, normalized_url=norm, body_hash=document_body_hash(md_b.markdown),
        )
        assert existing is None  # different body → no false merge
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M3/M4 — artifact persisted + provenance edges
# ---------------------------------------------------------------------------


async def test_cascade_persists_artifact_and_edges(seeded_graph, tmp_path, monkeypatch):
    """M3/M4: real loop → funnel → synthesis artifact + cites/supported_by edges."""
    db_path, emb = seeded_graph
    events = str(tmp_path / "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setattr(
        "substrate.graph.insight_question.graph_db_path", lambda: db_path,
    )

    register_provider(_CassetteProvider())
    loop_fn = real_research_loop(_deps(seeded_graph))
    funnel = PromotionFunnel(db_path=db_path, embedding_provider=emb)
    budget = BudgetManager()
    runner = HostLocalRunner(
        loop_fn, budget=budget, events_dir=events,
        seal_on_complete=False, on_emit=funnel.submit,
    )
    await funnel.start()
    plan = ResearchPlan(
        investigation_id="inv-spr07-artifact",
        sub_question="photosynthesis chloroplast light reaction",
        budget=BudgetCap(cost_usd=0.50),
    )
    handle = await runner.start("inv-spr07-artifact", plan)
    _ = [ev async for ev in runner.stream(handle)]
    await runner.join()
    await funnel.drain_and_stop()
    assert funnel.promoted_insights >= 1
    assert not funnel.errors, funnel.errors

    session_id = "session-spr07"
    con = connect_write(db_path, purpose="artifact-test")
    try:
        con.execute("BEGIN")
        result = persist_cascade_synthesis_artifact(
            con,
            session_id=session_id,
            investigation_id=session_id,
            provenance_state=funnel.provenance_state,
            embedding_provider=emb,
        )
        con.execute("COMMIT")
    finally:
        con.close()
    assert result is not None
    artifact_id = result.artifact_document_id

    con = connect_read(db_path)
    try:
        art = con.execute(
            "SELECT content_class, structured_blocks FROM documents WHERE document_id = ?",
            [artifact_id],
        ).fetchone()
        assert art is not None
        assert art[0] == PERSONAL_READING_CONTENT_CLASS
        assert art[1] is not None

        supported = con.execute(
            "SELECT count(*) FROM edges WHERE relation = 'supported_by' "
            "AND source_document_id IS NOT NULL",
        ).fetchone()[0]
        cites = con.execute(
            "SELECT count(*) FROM edges WHERE relation = ?",
            [CITES_RELATION],
        ).fetchone()[0]
        assert supported >= 1
        assert cites >= 1
    finally:
        con.close()


async def test_promotion_funnel_writes_supported_by_edge(seeded_graph, monkeypatch):
    db_path, emb = seeded_graph
    monkeypatch.setattr(
        "substrate.graph.insight_question.graph_db_path", lambda: db_path,
    )
    chunk_row = connect_read(db_path).execute(
        "SELECT chunk_id FROM chunks WHERE document_id = 'doc-spr04-1' LIMIT 1",
    ).fetchone()
    ev = _note_event(
        source_document_id="doc-spr04-1",
        source_kind="local_chunk",
        source_chunk_id=str(chunk_row[0]),
        all_source_document_ids=["doc-spr04-1"],
    )
    pre = resolve_sources_for_note(ev, db_path=db_path, embedding_provider=emb)
    con = connect_write(db_path, purpose="test")
    try:
        con.execute("BEGIN")
        promote_note_with_provenance(
            ev, con=con, embedding_provider=emb,
            db_path=db_path, resolved_sources=pre,
        )
        con.execute("COMMIT")
        n = con.execute(
            "SELECT count(*) FROM edges WHERE relation = 'supported_by' "
            "AND source_document_id = 'doc-spr04-1'",
        ).fetchone()[0]
        assert n >= 1
        meta = con.execute(
            "SELECT metadata FROM nodes WHERE node_type = 'insight' ORDER BY created_at DESC LIMIT 1",
        ).fetchone()
        assert meta and "doc-spr04-1" in (meta[0] or "")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Partial-failure paths (rigor #3)
# ---------------------------------------------------------------------------


def test_failed_fetch_skips_edge_not_orphan(seeded_graph, monkeypatch):
    db_path, emb = seeded_graph
    monkeypatch.setattr(
        "substrate.graph.insight_question.graph_db_path", lambda: db_path,
    )

    def _boom(_url):
        raise httpx.ConnectError("simulated", request=httpx.Request("GET", _WEB_URL))

    ev = _note_event(
        source_document_id=_WEB_URL,
        source_kind="web_url",
        source_url=_WEB_URL,
        all_source_document_ids=[_WEB_URL],
    )
    pre = resolve_sources_for_note(
        ev, db_path=db_path, embedding_provider=emb, url_fetcher=_boom,
    )
    con = connect_write(db_path, purpose="test")
    try:
        con.execute("BEGIN")
        nid = promote_note_with_provenance(
            ev, con=con, embedding_provider=emb,
            db_path=db_path, resolved_sources=pre,
        )
        con.execute("COMMIT")
        edges = con.execute(
            "SELECT count(*) FROM edges WHERE source_node_id = ? AND relation = 'supported_by'",
            [nid],
        ).fetchone()[0]
        assert edges == 0  # no orphan edge to missing source
        row = con.execute(
            "SELECT metadata FROM nodes WHERE node_id = ?", [nid],
        ).fetchone()
        meta = json.loads(row[0])
        assert "source_ingest_skipped" in meta
    finally:
        con.close()


def test_personal_reading_source_not_restamped_servable(seeded_graph, monkeypatch):
    db_path, emb = seeded_graph
    monkeypatch.setattr(
        "substrate.graph.insight_question.graph_db_path", lambda: db_path,
    )
    con = connect_write(db_path, purpose="test")
    try:
        insert_document(
            con,
            document_id="doc-restricted",
            source_tier=2,
            document_type="web_article",
            content_class=PERSONAL_READING_CONTENT_CLASS,
            raw_text="restricted body text",
        )
        insert_chunk(
            con, document_id="doc-restricted", chunk_index=0,
            text="restricted chunk", embedding=emb.encode("restricted chunk"),
        )
        chunk_id = con.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = 'doc-restricted'",
        ).fetchone()[0]
    finally:
        con.close()
    ev = _note_event(
        source_document_id="doc-restricted",
        source_kind="local_chunk",
        source_chunk_id=str(chunk_id),
        all_source_document_ids=["doc-restricted"],
    )
    pre = resolve_sources_for_note(ev, db_path=db_path, embedding_provider=emb)
    con = connect_write(db_path, purpose="test")
    try:
        con.execute("BEGIN")
        promote_note_with_provenance(
            ev, con=con, embedding_provider=emb,
            db_path=db_path, resolved_sources=pre,
        )
        con.execute("COMMIT")
        cc = con.execute(
            "SELECT content_class FROM documents WHERE document_id = 'doc-restricted'",
        ).fetchone()[0]
        assert cc == PERSONAL_READING_CONTENT_CLASS
    finally:
        con.close()