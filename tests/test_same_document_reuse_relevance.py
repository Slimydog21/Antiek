"""Same-document reuse relevance under ST-embedding similarity collapse.

Live spin-research seeds use the book passage as the question. Note-taker
insights are meta-research claims about that book; sentence-transformers
cosine to the passage is typically 0.05-0.10 — below RELEVANCE_FLOOR (0.25,
calibrated on hash embedders). Groundedness-passing same-document units must
still inject; cross-document low-cosine units must still drop.
"""

from __future__ import annotations

from substrate.context_pack import knowledge_reuse as kr
from substrate.contracts.nodes import KnowledgeUnitContract, ProvenanceLink, ServabilityTag


def _ru(*, node_id: str, sim: float, same: bool) -> kr.RetrievedUnit:
    unit = KnowledgeUnitContract(
        node_id=node_id,
        node_type="insight",
        text="A grounded claim about the book under study.",
        investigation_id="inv-src",
        confidence="high",
        retrieval_key=node_id,
        provenance=ProvenanceLink(source_document_id="doc-book", chunk_id="chunk-1"),
        servability=ServabilityTag(content_class="public_domain", serves_full_text=True),
        groundedness_score=0.62,
    )
    return kr.RetrievedUnit(
        unit=unit,
        similarity=sim,
        content_class="public_domain",
        taken_down=False,
        same_document=same,
    )


def test_same_document_low_cosine_survives_relevance_floor() -> None:
    low = _ru(node_id="insight-hi-g", sim=0.05, same=True)
    assert low.similarity < kr.RELEVANCE_FLOOR
    injected, decisions, coverage = kr.partition_units(
        [low], budget=4000, relevance_floor=kr.RELEVANCE_FLOOR
    )
    assert coverage.dropped_not_servable == 0
    assert coverage.dropped_low_relevance == 0
    assert [u.unit_id for u in injected] == ["insight-hi-g"]
    assert decisions[0].decision == kr.DECISION_INJECTED


def test_cross_document_low_cosine_still_dropped() -> None:
    low = _ru(node_id="insight-other", sim=0.05, same=False)
    injected, decisions, coverage = kr.partition_units(
        [low], budget=4000, relevance_floor=kr.RELEVANCE_FLOOR
    )
    assert coverage.dropped_low_relevance == 1
    assert injected == []
    assert decisions[0].decision == kr.DECISION_LOW_RELEVANCE


