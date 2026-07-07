"""Capstone E2E: the owner's personal_reading compounds through the REAL
production callers — the D2 owner-private-reuse unblock, proven end-to-end.

Pre-D2 the flywheel compounded ONLY for public_domain content: the reuse gate's
sole bar was the public §9.0 ``serves_full_text`` tag, which bars
``personal_reading`` (the owner's own fetched third-party reading) — so even on
the owner's OWN private investigation the owner's reading could never compound
into the owner's research. That is the #1 thought-partner blocker: the
operator's real library (personal_reading + NULL content_class) never fed the
flywheel.

D2 (#209 gate + the host_local ``owner=True`` wiring) adds the owner-readable
track: on the owner path a grounded unit whose source the owner may read in
full (servable ∪ personal_reading, not taken_down) is reusable — mirroring the
``owner`` switch already shipped in books/serve.py.

This test exercises the un-bridged chain with a PERSONAL_READING document:

  * run-1 deposits a note derived from a personal_reading doc via the REAL
    ``PromotionFunnel``. The promoted node is NON-SERVABLE publicly
    (PERSONAL_READABLE) — the leak guard: a private synthesis can never go
    public without re-gating.
  * run-2 starts a second research via the REAL ``HostLocalRunner`` with a
    ``RetrievalSubstrate`` (the production reuse caller,
    ``_maybe_reuse_prior_knowledge`` wired ``owner=True``) → exactly one
    ``knowledge.reused`` with NON-EMPTY ``reused_unit_ids``. The owner's
    reading compounds into the owner's research.
  * control: the same retrieved unit is EXCLUDED by ``filter_reusable`` with
    ``owner=False`` (the public path stays byte-identical — owner widens
    nothing publicly).

If this regresses, either the owner wiring was dropped (host_local no longer
passes ``owner=True``) or the content_class stamping in ``retrieve_prior_units``
broke (the owner-readable track lost its document-side input).
"""

from __future__ import annotations

import json
import os

import duckdb
import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from runtime.research_runner import (
    HostLocalRunner,
    PromotionFunnel,
    ResearchPlan,
    make_contract_gather_stub,
)
from runtime.research_runner.protocol import StepEvent
from substrate.event_log import trajectory
from substrate.graph.retrieval_substrate import make_substrate
from substrate.graph.schema import init_database_at_path

_BODY = (
    "Subclutter visibility quantifies a radar's ability to detect moving "
    "targets against a background of clutter. The metric binds the signal-to-"
    "clutter ratio to the detection threshold, setting the floor on the "
    "smallest target velocity a given waveform can resolve. "
)
_NOTE = (
    "Subclutter visibility binds the signal-to-clutter ratio to the detection "
    "threshold, setting the floor on the smallest target velocity a waveform "
    "can resolve."
)


def _seed_personal_reading_doc(db_path: str, emb: HashEmbedding) -> None:
    con = connect_write(db_path, purpose="seed-owner-private")
    try:
        con.execute("BEGIN")
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, "
            "document_type, content_class) VALUES (?, ?, 1, 'paper', 'personal_reading')",
            ["doc-owner", "Owner personal-reading doc"],
        )
        text = _BODY * 4
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "embedding, token_count) VALUES (?, ?, 0, ?, ?, ?)",
            ["chunk-owner", "doc-owner", text, emb.encode(text), max(1, len(text) // 4)],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def _plan(iid: str, sub_q: str) -> ResearchPlan:
    return ResearchPlan(investigation_id=iid, sub_question=sub_q)


@pytest.fixture
def emb() -> HashEmbedding:
    return HashEmbedding()


@pytest.fixture(autouse=True)
def _events(monkeypatch, tmp_path):
    ev = os.path.join(tmp_path, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    return ev


@pytest.mark.asyncio
async def test_personal_reading_compounds_on_owner_path_and_leakguards_public(emb, tmp_path) -> None:
    """A personal_reading note deposits NON-SERVABLE (leak guard) yet still
    compounds through the REAL host_local owner path (owner=True wired)."""
    db = str(tmp_path / "graph-owner.duckdb")
    init_database_at_path(db)
    _seed_personal_reading_doc(db, emb)
    events_dir = os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]

    # Run 1 — REAL funnel deposit of a personal_reading-derived note.
    funnel = PromotionFunnel(db_path=db, embedding_provider=emb)
    await funnel.start()
    await funnel.submit(
        StepEvent("inv-owner-1", 0, "note", text=_NOTE, data={"document_id": "doc-owner"})
    )
    await funnel.drain_and_stop()
    assert funnel.errors == []
    assert funnel.promoted_insights == 1

    node_id = funnel.promoted_node_ids[0]
    rc = duckdb.connect(db, read_only=True)
    meta = rc.execute("SELECT metadata FROM nodes WHERE node_id = ? LIMIT 1", [node_id]).fetchone()
    node_meta = json.loads(meta[0]) if meta and meta[0] else {}
    assert node_meta.get("chunk_id") == "chunk-owner", "funnel did not ground the note (#263)"

    # Leak guard: the promoted node's content_class resolves to personal_reading,
    # which projects to PERSONAL_READABLE — NON-SERVABLE publicly. A private
    # synthesis derived from personal_reading can never serve full text without
    # re-gating. This is the deposit-side half of D2's rights boundary.
    from substrate.graph.insight_question import knowledge_unit_of

    unit = knowledge_unit_of(rc, node_id=node_id)
    rc.close()
    assert unit is not None, "knowledge_unit_of must assemble the funnel-promoted node"
    assert unit.servability.serves_full_text is False, (
        "a personal_reading-derived note must deposit NON-SERVABLE publicly "
        "(PERSONAL_READABLE) — the leak guard"
    )

    # Run 2 — REAL host_local reuse (owner=True is now wired into the caller).
    sub = make_substrate("brute_force", db, model=emb)
    try:
        runner2 = HostLocalRunner(
            make_contract_gather_stub(steps=1, cost_per_step=0.0),
            events_dir=events_dir,
            seal_on_complete=False,
            retrieval_substrate=sub,
        )
        h2 = await runner2.start("inv-owner-2", _plan("inv-owner-2", _NOTE))
        _ = [ev async for ev in runner2.stream(h2)]
        await runner2.join()
    finally:
        sub.close()

    reused = [r for r in trajectory("inv-owner-2") if r["action_type"] == "knowledge.reused"]
    assert len(reused) == 1, "host_local.start must emit exactly one knowledge.reused"
    payload = reused[0]["payload"]
    assert payload["reused_unit_ids"], (
        "the owner's personal_reading must compound into the owner's research — "
        "empty reused_unit_ids mean the owner path (owner=True) is not wired or "
        "the content_class stamping broke"
    )

    # Control: the SAME unit, gated on the PUBLIC path (owner=False), is
    # excluded. owner widens nothing publicly — byte-identity holds.
    from substrate.context_pack.knowledge_reuse import retrieve_prior_units
    from substrate.flywheel.reuse_gate import filter_reusable

    sub_ctrl = make_substrate("brute_force", db, model=emb)
    try:
        candidates = retrieve_prior_units(sub_ctrl, question_text=_NOTE)
        assert candidates, "retrieve_prior_units must find the personal_reading unit"
        reusable_pub, _ = filter_reusable(
            candidates, investigation_id="inv-ctrl", events_dir=events_dir, emit=False,
        )
        assert reusable_pub == [], (
            "the PUBLIC path must exclude personal_reading — owner=True widens "
            "nothing publicly (byte-identity regression)"
        )
    finally:
        sub_ctrl.close()
