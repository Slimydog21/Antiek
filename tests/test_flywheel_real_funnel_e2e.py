"""Capstone E2E: the compounding flywheel turns through the REAL production
deposit + reuse callers — no test bridge.

The sibling ``test_flywheel_reuse.py`` proves the emit path but bridges run-1's
deposit with ``_ground_gather_note`` because the funnel's promote path
historically landed non-servable, ungrounded nodes (``chunk_id=None``,
``content_class=None``). Two fixes closed that gap:

  * #263 — ``PromotionFunnel._promote`` grounds each note on a real chunk
    (``chunk_id``), so ``knowledge_unit_of`` can assemble it.
  * #274 — ``knowledge_unit_of`` resolves ``content_class`` from the source
    document, so a public_domain chunk's insight is SERVABLE and the SPR-08
    trust gate admits it.

This test exercises the un-bridged chain: a public_domain note deposited via
the REAL ``PromotionFunnel`` (the production ``on_emit`` caller) → a second
research started via the REAL ``HostLocalRunner`` with a ``RetrievalSubstrate``
(the production reuse caller, ``_maybe_reuse_prior_knowledge``) → exactly one
``knowledge.reused`` event with NON-EMPTY ``reused_unit_ids``. This is the
observable signature of compounding (the Cursor-for-knowledge vision): a later
question reuses a prior distilled insight, not the empty-units placeholder.

If this test regresses, the flywheel's reuse half is structurally starved again
— investigate the funnel grounding (#263) and the content_class resolution
(#274) before anything else.
"""

from __future__ import annotations

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
    "Neutral atom qubit error rate suppression improved materially this "
    "quarter. The two-qubit gate error rate for neutral atom systems fell "
    "below the 1e-3 threshold, a scaling milestone for the platform. Arrays "
    "of individually trapped neutral atoms now reach gate fidelities that "
    "make fault-tolerant computation plausible at scale. "
)
_NOTE = (
    "Neutral-atom two-qubit gate error rate fell below the 1e-3 threshold "
    "this quarter, a scaling milestone."
)


def _seed_public_doc(db_path: str, emb: HashEmbedding) -> None:
    con = connect_write(db_path, purpose="seed")
    try:
        con.execute("BEGIN")
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, "
            "document_type, content_class) VALUES (?, ?, 1, 'paper', 'public_domain')",
            ["doc-e2e", "E2E public doc"],
        )
        text = _BODY * 4
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "embedding, token_count) VALUES (?, ?, 0, ?, ?, ?)",
            ["chunk-e2e", "doc-e2e", text, emb.encode(text), max(1, len(text) // 4)],
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
async def test_real_funnel_deposit_then_host_local_reuse_injects(emb, tmp_path) -> None:
    """Run-1 deposits a public_domain note via the REAL funnel (no bridge);
    run-2 starts a second research via the REAL host_local runner with a
    RetrievalSubstrate and must emit one knowledge.reused with non-empty
    reused_unit_ids — the flywheel compounds."""
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    _seed_public_doc(db, emb)
    events_dir = os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]

    # Run 1 — REAL funnel deposit. The note carries the source document_id,
    # so the funnel grounds it on the chunk (#263) and resolves content_class
    # to public_domain (#274) -> servable. No _ground_gather_note bridge.
    funnel = PromotionFunnel(db_path=db, embedding_provider=emb)
    await funnel.start()
    await funnel.submit(
        StepEvent("inv-e2e-1", 0, "note", text=_NOTE, data={"document_id": "doc-e2e"})
    )
    await funnel.drain_and_stop()
    assert funnel.errors == []
    assert funnel.promoted_insights == 1

    # Sanity: the funnel-promoted node is genuinely grounded + servable now
    # (the property both fixes restore). If this regresses, the reuse below
    # cannot inject and the assertion at the end fails informatively.
    rc = duckdb.connect(db, read_only=True)
    meta = rc.execute(
        "SELECT metadata FROM nodes WHERE node_id = ? LIMIT 1",
        [funnel.promoted_node_ids[0]],
    ).fetchone()
    import json
    node_meta = json.loads(meta[0]) if meta and meta[0] else {}
    assert node_meta.get("chunk_id") == "chunk-e2e", (
        "funnel did not ground the note on a chunk (#263 regressed)"
    )

    # Run 2 — REAL host_local runner reuse path (_maybe_reuse_prior_knowledge).
    sub = make_substrate("brute_force", db, model=emb)
    try:
        runner2 = HostLocalRunner(
            make_contract_gather_stub(steps=1, cost_per_step=0.0),
            events_dir=events_dir,
            seal_on_complete=False,
            retrieval_substrate=sub,
        )
        h2 = await runner2.start("inv-e2e-2", _plan("inv-e2e-2", _NOTE))
        _ = [ev async for ev in runner2.stream(h2)]
        await runner2.join()
    finally:
        sub.close()

    reused = [r for r in trajectory("inv-e2e-2") if r["action_type"] == "knowledge.reused"]
    assert len(reused) == 1, "host_local.start must emit exactly one knowledge.reused"
    payload = reused[0]["payload"]
    assert payload["reused_unit_ids"], (
        "the flywheel must inject the prior servable public-domain unit — "
        "empty reused_unit_ids mean the deposit/reuse contract is starved again"
    )
    assert len(payload["reused_unit_ids"]) == len(payload["scores"])
