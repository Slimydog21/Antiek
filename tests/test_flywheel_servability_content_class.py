"""Regression: knowledge_unit_of resolves content_class from the source
document, so a public_domain chunk's insight is SERVABLE and the flywheel's
reuse half actually injects it.

Before the fix, ``knowledge_unit_of`` computed servability as
``servability_tag_for(content_class)`` using only the caller-supplied
``content_class`` parameter, which the reuse retrieve path resolves via a
``supported_by``-edge join. The funnel deposits notes with no ``supported_by``
claim node (so that join yields NULL), so every funnel-promoted unit was
flattened to ``content_class=None`` → deny-by-default ``GATED_METADATA_ONLY``
→ ``serves_full_text=False`` → dropped by the SPR-08 trust gate as
``non-servable``. The unit was grounded (chunk_id stamped) and retrieved, but
never injected — the compounding flywheel was structurally starved for ALL
funnel-deposited knowledge, even public-domain content that is unambiguously
servable.

``knowledge_unit_of`` now resolves ``content_class`` from the source
document when the caller supplies None (a read-only SELECT on the same
connection, §16-safe). This is a content-rights fix (public vs gated),
DISTINCT from the operator-gated D2/#209 owner-private audience boundary.
"""

from __future__ import annotations

import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from runtime.research_runner import PromotionFunnel
from runtime.research_runner.protocol import StepEvent
from substrate.context_pack.knowledge_reuse import (
    assemble_context_pack_with_reuse,
    retrieve_prior_units,
)
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


def _seed_doc(
    db_path: str,
    emb: HashEmbedding,
    *,
    doc_id: str,
    chunk_id: str,
    content_class: str | None,
) -> None:
    con = connect_write(db_path, purpose="seed")
    try:
        con.execute("BEGIN")
        if not con.execute(
            "SELECT 1 FROM documents WHERE document_id = ?", [doc_id]
        ).fetchone():
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
                [doc_id, doc_id, content_class],
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
async def test_public_domain_funnel_unit_is_servable_and_injected(emb, tmp_path) -> None:
    """A funnel-promoted note grounded on a public_domain chunk is servable
    (serves_full_text=True) AND injected into a reuse pack — the flywheel
    turns for public-domain knowledge. Before the fix both failed: the unit
    was dropped as non-servable and reuse_injected was False."""
    import duckdb

    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    _seed_doc(db, emb, doc_id="doc-pub", chunk_id="chunk-pub", content_class="public_domain")

    funnel = PromotionFunnel(db_path=db, embedding_provider=emb)
    await funnel.start()
    await funnel.submit(
        StepEvent("inv-pub", 0, "note", text=_NOTE, data={"document_id": "doc-pub"})
    )
    await funnel.drain_and_stop()
    assert funnel.errors == []
    nid = funnel.promoted_node_ids[0]

    rc = duckdb.connect(db, read_only=True)
    unit = knowledge_unit_of(rc, nid, content_class=None, score_groundedness=True)
    assert unit.servability.serves_full_text is True, (
        "public_domain funnel unit must be servable; got "
        f"{unit.servability!r}"
    )

    sub = make_substrate("brute_force", db_path=db, model=emb)
    units = retrieve_prior_units(
        sub, question_text=_NOTE, policy_tag="attribution_eligible", limit=10
    )
    assert len(units) == 1
    pack = assemble_context_pack_with_reuse(
        role="synthesizer", investigation_id="inv-pub", layers=[], units=units,
        events_dir=str(tmp_path / "ev-pub"),
    )
    assert pack.reuse_injected is True, "flywheel must inject a servable public unit"
    assert len(pack.injected) == 1
    assert pack.coverage.dropped_by_trust_gate == 0


@pytest.mark.asyncio
async def test_gated_funnel_unit_stays_non_servable(emb, tmp_path) -> None:
    """A funnel-promoted note grounded on a document with NULL/unknown
    content_class stays deny-by-default non-servable (rights unknown = gated).
    The fix must NOT over-servable content — unknown rights remain withheld."""
    import duckdb

    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    _seed_doc(db, emb, doc_id="doc-unknown", chunk_id="chunk-unknown",
              content_class=None)

    funnel = PromotionFunnel(db_path=db, embedding_provider=emb)
    await funnel.start()
    await funnel.submit(
        StepEvent("inv-unk", 0, "note", text=_NOTE, data={"document_id": "doc-unknown"})
    )
    await funnel.drain_and_stop()
    nid = funnel.promoted_node_ids[0]

    rc = duckdb.connect(db, read_only=True)
    unit = knowledge_unit_of(rc, nid, content_class=None, score_groundedness=True)
    assert unit.servability.serves_full_text is False, (
        "unknown-rights content must stay deny-by-default non-servable"
    )
