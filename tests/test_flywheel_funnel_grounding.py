"""Regression: PromotionFunnel grounds promoted notes on a real chunk.

Before the fix, ``PromotionFunnel._promote`` called ``promote_insight`` /
``promote_question`` with ``source_document_id`` but NO ``chunk_id``, so every
funnel-promoted node landed with ``chunk_id=None`` and no ``supported_by``
edge. The flywheel's reuse half (``knowledge_unit_of``) requires a
claim→chunk→doc grounding, so it rejected EVERY candidate and
``retrieve_prior_units`` returned ``[]`` — the deposit and reuse contracts
were structurally disconnected, which is why ``knowledge_reuse_count`` stayed
0 even though the ``knowledge.reused`` event itself emits correctly.

The funnel now resolves a substantive chunk of the note's source document
(mirroring ``tools.run_investigation._pick_substantive_chunk``) and threads
``chunk_id`` into the promote call, so funnel-promoted units are grounded and
retrievable.

NOTE: injection into a reuse pack is still gated downstream by the §9.0
servability classifier (deny-by-default) — the operator-gated rights/reuse
boundary (D2/#209). That is deliberately out of scope here; this test asserts
only the deposit-grounding contract the funnel owns.
"""

from __future__ import annotations

import duckdb
import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from runtime.research_runner import PromotionFunnel
from runtime.research_runner.protocol import StepEvent
from substrate.context_pack.knowledge_reuse import retrieve_prior_units
from substrate.graph.insight_question import knowledge_unit_of
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


def _seed_doc_with_chunk(db_path: str, emb: HashEmbedding, *, doc_id: str, chunk_id: str) -> None:
    con = connect_write(db_path, purpose="seed")
    try:
        con.execute("BEGIN")
        if not con.execute(
            "SELECT 1 FROM documents WHERE document_id = ?", [doc_id]
        ).fetchone():
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, content_class) VALUES (?, ?, 1, 'paper', 'public_domain')",
                [doc_id, doc_id],
            )
        text = _BODY * 4
        if not con.execute(
            "SELECT 1 FROM chunks WHERE chunk_id = ?", [chunk_id]
        ).fetchone():
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                "embedding, token_count) VALUES (?, ?, 0, ?, ?, ?)",
                [chunk_id, doc_id, text, emb.encode(text), max(1, len(text) // 4)],
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


@pytest.fixture
def emb() -> HashEmbedding:
    return HashEmbedding()


@pytest.mark.asyncio
async def test_funnel_promotes_grounded_retrievable_insight(emb, tmp_path) -> None:
    """A funnel-promoted note with a real source document is grounded
    (``knowledge_unit_of`` assembles it) and returned by
    ``retrieve_prior_units``. Before the fix both failed: ValueError +
    empty retrieval."""
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    _seed_doc_with_chunk(db, emb, doc_id="doc-ground-1", chunk_id="chunk-ground-1")

    funnel = PromotionFunnel(db_path=db, embedding_provider=emb)
    await funnel.start()
    await funnel.submit(
        StepEvent("inv-ground", 0, "note", text=_NOTE, data={"document_id": "doc-ground-1"})
    )
    await funnel.drain_and_stop()

    assert funnel.errors == []
    assert funnel.promoted_insights == 1
    nid = funnel.promoted_node_ids[0]

    rc = duckdb.connect(db, read_only=True)
    # (1) grounded — knowledge_unit_of assembles it (was: ValueError, chunk_id=None)
    unit = knowledge_unit_of(rc, nid, content_class=None, score_groundedness=True)
    assert unit is not None

    # (2) retrievable — retrieve_prior_units returns it (was: [])
    sub = make_substrate("brute_force", db_path=db, model=emb)
    units = retrieve_prior_units(
        sub, question_text=_NOTE, policy_tag="attribution_eligible", limit=10
    )
    assert len(units) >= 1, "deposit/reuse contract disconnected: no units retrieved"


@pytest.mark.asyncio
async def test_funnel_note_without_document_stays_ungrounded(emb, tmp_path) -> None:
    """A note carrying no source document has no chunk to resolve, so
    ``chunk_id`` stays None and the node is not recoverable as a knowledge
    unit. Prior behaviour for un-groundable notes is preserved (no regression,
    no fabricated grounding)."""
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)

    funnel = PromotionFunnel(db_path=db, embedding_provider=emb)
    await funnel.start()
    await funnel.submit(
        StepEvent("inv-nodoc", 0, "note", text="A floating note with no document provenance.")
    )
    await funnel.drain_and_stop()

    assert funnel.errors == []
    assert funnel.promoted_insights == 1
    rc = duckdb.connect(db, read_only=True)
    with pytest.raises(ValueError):
        knowledge_unit_of(
            rc, funnel.promoted_node_ids[0], content_class=None, score_groundedness=True
        )
