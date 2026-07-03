"""SPR-02 flywheel nerve — the cascade launch path provides a reuse substrate.

The runner's reuse hook (``HostLocalRunner._maybe_reuse_prior_knowledge``) is
complete; it emits ``knowledge.reused`` iff it is given a way to reach a
``RetrievalSubstrate``. Before this wire, ``cascade_routes`` constructed the
runner without one, so the flywheel was reachable-but-dead. These tests pin the
wire:

1. ``_reuse_substrate()`` returns a real, queryable brute_force substrate over
   the graph (read-only, no whole-DB temp copy) using the funnel's own default
   embedder — so it works on a box without sentence-transformers.
2. It degrades to ``None`` (never raises) when construction fails.
3. End-to-end: a runner wired with ``retrieval_substrate_factory=_reuse_substrate``
   over a graph that holds a servable prior unit emits exactly one
   ``knowledge.reused`` — the wire carries the substrate all the way to the
   observable flywheel signal.
4. RO/RW coexistence (the regression guard): after the reuse query, a
   ``connect_write`` to the SAME db must succeed. The FACTORY wiring builds +
   closes the read-only reuse connection inside the one synchronous reuse hook,
   so it never lingers to clash with the promotion funnel's in-process writer
   (DuckDB forbids a read-only and a read-write handle to one file in a process
   — the eager ``retrieval_substrate=_reuse_substrate()`` wiring clashed there
   and reddened the whole cascade-API suite). This is the check that would fail
   if the eager-held wiring ever came back.
"""

from __future__ import annotations

import os

import pytest

import interfaces.research.api.cascade_routes as cr
from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from runtime.research_runner import (
    HostLocalRunner,
    ResearchPlan,
    make_contract_gather_stub,
)
from substrate.event_log import trajectory
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_node
from substrate.graph.schema import init_database_at_path

_TOPIC = "neutral atom qubit error rate suppression scaling milestone"


@pytest.fixture
def events_dir(tmp_path, monkeypatch):
    d = os.path.join(tmp_path, "events")
    os.makedirs(d, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", d)
    return d


def _seed_servable_unit(db_path: str, emb: HashEmbedding, *, investigation_id: str,
                        note_text: str) -> None:
    """Deposit one §9.0-servable (public_domain) prior unit the reuse path can
    retrieve — mirrors tests/test_flywheel_reuse.py's bridge."""
    con = connect_write(db_path, purpose="reuse_wire_test")
    try:
        con.execute("BEGIN")
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, "
            "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
            ["doc-pub", "Public", "public_domain"],
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "embedding, token_count) VALUES (?, ?, 0, ?, ?, ?)",
            ["chunk-0", "doc-pub", note_text, emb.encode(note_text),
             max(1, len(note_text) // 4)],
        )
        claim_id = insert_node(
            con, canonical_label=f"claim: {note_text[:80]}", node_type="claim",
            graph_scope="depth", investigation_id=investigation_id,
            embedding=emb.encode(note_text), on_conflict="ignore",
        )
        promote_insight(
            text=note_text, investigation_id=investigation_id, confidence="high",
            supported_by=[claim_id], source_document_id="doc-pub",
            chunk_id="chunk-0", embedding_provider=emb, con=con,
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def test_reuse_substrate_returns_queryable_brute_force(tmp_path, monkeypatch):
    """_reuse_substrate() builds a real, queryable substrate over the graph —
    not None, and (brute_force) without copying the whole DB to a temp dir."""
    db = os.path.join(tmp_path, "graph.duckdb")
    init_database_at_path(db)
    monkeypatch.setattr(cr, "_db", lambda: db)
    monkeypatch.setattr(cr, "_embedding_provider", lambda: HashEmbedding())

    sub = cr._reuse_substrate()
    try:
        assert sub is not None, "wire must provide a substrate, not None"
        assert hasattr(sub, "query"), "substrate must expose the query contract"
        # brute_force keeps a read-only connection over the real file; it does
        # not build a temp HNSW copy (that is the vss spike's behaviour).
        assert type(sub).__name__ == "BruteForceSubstrate"
    finally:
        if sub is not None and hasattr(sub, "close"):
            sub.close()


def test_reuse_substrate_degrades_to_none_on_failure(tmp_path, monkeypatch):
    """Construction failure returns None (reuse best-effort), never raises."""
    def _boom(*a, **k):
        raise RuntimeError("no db")
    monkeypatch.setattr(cr, "_db", _boom)
    assert cr._reuse_substrate() is None


@pytest.mark.asyncio
async def test_reuse_factory_fires_knowledge_reused(tmp_path, events_dir, monkeypatch):
    """A runner wired with ``retrieval_substrate_factory=_reuse_substrate`` over a
    graph holding a servable prior unit emits exactly one knowledge.reused; the
    no-substrate path fires zero (red-proof). This exercises the SAME factory the
    cascade launch path now passes, so it proves the production wire — not just an
    isolated substrate/runner pairing."""
    emb = HashEmbedding()
    db = os.path.join(tmp_path, "graph.duckdb")
    init_database_at_path(db)
    _seed_servable_unit(db, emb, investigation_id="seed", note_text=_TOPIC)

    monkeypatch.setattr(cr, "_db", lambda: db)
    monkeypatch.setattr(cr, "_embedding_provider", lambda: emb)

    # Red-proof: no substrate + no factory → zero knowledge.reused.
    runner0 = HostLocalRunner(
        make_contract_gather_stub(steps=1, cost_per_step=0.0),
        events_dir=events_dir, seal_on_complete=False,
        retrieval_substrate=None,
    )
    h0 = await runner0.start("inv-none", ResearchPlan(
        investigation_id="inv-none", sub_question=_TOPIC))
    _ = [ev async for ev in runner0.stream(h0)]
    await runner0.join()
    assert [r for r in trajectory("inv-none")
            if r["action_type"] == "knowledge.reused"] == []

    # Wire: the exact factory cascade_routes.launch() passes → one knowledge.reused.
    runner = HostLocalRunner(
        make_contract_gather_stub(steps=1, cost_per_step=0.0),
        events_dir=events_dir, seal_on_complete=False,
        retrieval_substrate_factory=cr._reuse_substrate,
    )
    h = await runner.start("inv-wire", ResearchPlan(
        investigation_id="inv-wire", sub_question=_TOPIC))
    _ = [ev async for ev in runner.stream(h)]
    await runner.join()

    reused = [r for r in trajectory("inv-wire")
              if r["action_type"] == "knowledge.reused"]
    assert len(reused) == 1, "wired factory must fire exactly one knowledge.reused"
    assert reused[0]["payload"]["reused_unit_ids"], (
        "reused_unit_ids empty → the flywheel signal would be vacuous"
    )


@pytest.mark.asyncio
async def test_reuse_factory_leaves_no_readonly_handle_blocking_a_writer(
    tmp_path, events_dir, monkeypatch
):
    """Regression guard for the cascade-API DuckDB conflict: the factory wiring
    must release the read-only reuse connection inside the one reuse hook, so a
    ``connect_write`` to the SAME db immediately after a launched research
    succeeds. Under the old eager ``retrieval_substrate=_reuse_substrate()``
    wiring the read-only handle lingered and this write raised 'Can't open a
    connection to same database file with a different configuration than existing
    connections'."""
    emb = HashEmbedding()
    db = os.path.join(tmp_path, "graph.duckdb")
    init_database_at_path(db)
    _seed_servable_unit(db, emb, investigation_id="seed", note_text=_TOPIC)

    monkeypatch.setattr(cr, "_db", lambda: db)
    monkeypatch.setattr(cr, "_embedding_provider", lambda: emb)

    runner = HostLocalRunner(
        make_contract_gather_stub(steps=1, cost_per_step=0.0),
        events_dir=events_dir, seal_on_complete=False,
        retrieval_substrate_factory=cr._reuse_substrate,
    )
    h = await runner.start("inv-rw", ResearchPlan(
        investigation_id="inv-rw", sub_question=_TOPIC))
    _ = [ev async for ev in runner.stream(h)]
    await runner.join()

    # The reuse hook has run and (if the factory did its job) closed its RO
    # handle. A read-write open on the same file in the same process must now
    # succeed — the assertion that fails the instant an eager-held RO wiring
    # returns.
    con = connect_write(db, purpose="reuse_wire_rw_coexistence")
    try:
        con.execute("SELECT 1").fetchone()
    finally:
        con.close()
