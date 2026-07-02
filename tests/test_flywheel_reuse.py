"""SPR-DRL-07 — two-run flywheel hermetic: knowledge.reused on second start.

Run 1 deposits prior knowledge via contract_gather_stub + PromotionFunnel
(ANT-DRL honest gather path). The stub promotes non-servable insight rows
today; the test completes the deposit shape Exa will produce by grounding
one servable unit on the gather note text — documented bridge, not a claim
that MOCK economics compound.

Run 2 starts a second contract_gather research with a RetrievalSubstrate on
the same graph and overlapping sub_question; host_local.start emits exactly
one knowledge.reused with non-empty reused_unit_ids before the first step.
"""

from __future__ import annotations

import os

import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from runtime.research_runner import (
    HostLocalRunner,
    PromotionFunnel,
    ResearchPlan,
    make_contract_gather_stub,
)
from substrate.event_log import trajectory
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_node
from substrate.graph.retrieval_substrate import make_substrate
from substrate.graph.schema import init_database_at_path

_TOPIC = "neutral atom qubit error rate suppression scaling milestone"


def _plan(iid: str, sub_q: str) -> ResearchPlan:
    return ResearchPlan(investigation_id=iid, sub_question=sub_q)


def _ground_gather_note(
    db_path: str,
    emb: HashEmbedding,
    *,
    investigation_id: str,
    note_text: str,
) -> str:
    """Deposit one §9.0-servable unit matching the gather note — test bridge."""
    con = connect_write(db_path, purpose="flywheel_reuse_test")
    try:
        con.execute("BEGIN")
        doc_id = "doc-gather-public"
        chunk_id = "chunk-gather-0"
        if not con.execute(
            "SELECT 1 FROM documents WHERE document_id = ?", [doc_id],
        ).fetchone():
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
                [doc_id, "Gather public", "public_domain"],
            )
        if not con.execute(
            "SELECT 1 FROM chunks WHERE chunk_id = ?", [chunk_id],
        ).fetchone():
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                "embedding, token_count) VALUES (?, ?, 0, ?, ?, ?)",
                [
                    chunk_id, doc_id, note_text, emb.encode(note_text),
                    max(1, len(note_text) // 4),
                ],
            )
        claim_id = insert_node(
            con,
            canonical_label=f"claim: {note_text[:80]}",
            node_type="claim",
            graph_scope="depth",
            investigation_id=investigation_id,
            embedding=emb.encode(note_text),
            on_conflict="ignore",
        )
        nid = promote_insight(
            text=note_text,
            investigation_id=investigation_id,
            confidence="high",
            supported_by=[claim_id],
            source_document_id=doc_id,
            chunk_id=chunk_id,
            embedding_provider=emb,
            con=con,
        )
        con.execute("COMMIT")
        return nid
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


@pytest.fixture
def emb():
    return HashEmbedding()


@pytest.fixture(autouse=True)
def _events(monkeypatch, tmp_path):
    ev = os.path.join(tmp_path, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    return ev


@pytest.mark.asyncio
async def test_two_run_contract_gather_emits_knowledge_reused_on_second_start(
    emb, tmp_path,
):
    """P-15 / SPR-DRL-07: second hermetic start emits knowledge.reused."""
    db = os.path.join(tmp_path, "graph.duckdb")
    init_database_at_path(db)
    events_dir = os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]

    funnel = PromotionFunnel(db_path=db, embedding_provider=emb)
    await funnel.start()

    runner1 = HostLocalRunner(
        make_contract_gather_stub(steps=1, cost_per_step=0.0),
        events_dir=events_dir,
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    h1 = await runner1.start("inv-run-1", _plan("inv-run-1", _TOPIC))
    _ = [ev async for ev in runner1.stream(h1)]
    await runner1.join()
    await funnel.drain_and_stop()

    note_text = (
        f"[gather-stub] provisional note from inv-run-1: {_TOPIC}"
    )
    _ground_gather_note(
        db, emb, investigation_id="inv-run-1", note_text=note_text,
    )

    sub = make_substrate("brute_force", db, model=emb)
    try:
        runner2 = HostLocalRunner(
            make_contract_gather_stub(steps=1, cost_per_step=0.0),
            events_dir=events_dir,
            seal_on_complete=False,
            retrieval_substrate=sub,
        )
        h2 = await runner2.start(
            "inv-run-2",
            _plan("inv-run-2", "neutral atom qubit error rate suppression"),
        )
        _ = [ev async for ev in runner2.stream(h2)]
        await runner2.join()
    finally:
        sub.close()

    rows = trajectory("inv-run-2")
    reused = [r for r in rows if r["action_type"] == "knowledge.reused"]
    assert len(reused) == 1
    payload = reused[0]["payload"]
    assert payload["reused_unit_ids"], (
        "second run must inject prior servable units — empty ids mean "
        "the flywheel observability gate is vacuous"
    )
    assert len(payload["reused_unit_ids"]) == len(payload["scores"])