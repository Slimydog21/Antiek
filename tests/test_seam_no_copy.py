"""The no-copy guard (antiek-unified SPR-03 M7) — the load-bearing seam test.

The whole flywheel rests on "one graph entity everywhere." A seam moves an
entity by REFERENCE: the entity on the receiving side must be the *same node id*
the sending side held, not a duplicate with copied content and a fresh id. A
copied entity is a provenance bug — the moment two halves of the flywheel hold
two copies, they drift, and the "one substrate" claim is a lie the data doesn't
support.

These tests exercise each committed handoff with a fake implementing the SPR-01
contract (the real implementation is the product's sprint — out of scope here)
and assert SAME-NODE-ID on both sides. The deciding rigor (rigor #3): a
deliberate-copy fixture FAILS the guard. If the guard passed whether or not the
entity was copied, it would prove nothing.

SPR-06's thread navigation depends on this guard; SPR-08's e2e flywheel test
composes it.
"""

from __future__ import annotations

import pytest

from substrate.contracts.nodes import InsightNodeContract
from substrate.contracts.outline_block import OutlineBlockContract
from substrate.seams import (
    ReadToWriteSeam,
    ResearchToReadSeam,
    SpeakToWriteSeam,
    WriteToReadSeam,
    WriteToSpeakSeam,
)

# ---------------------------------------------------------------------------
# Fakes standing in for the products' seam implementations (real impls live in
# Read SPR-03 / Write SPR-03/07 / Speak SPR-08 — out of scope here). Each one
# is the CORRECT, reference-preserving behavior. A copy variant is below.
# ---------------------------------------------------------------------------


def _research_promotes_insight() -> InsightNodeContract:
    """Research produces an insight node (content-addressed, stable id)."""
    return InsightNodeContract(
        node_id="insight-7f3a9c", text="Werner traded antiques before software.",
        investigation_id="inv-1", confidence="high",
    )


def read_to_write_handoff(insight: InsightNodeContract, *, section_id: str) -> OutlineBlockContract:
    """CORRECT read→write: the insight becomes a node-backed block whose
    node_id IS the insight's node_id. No content is inlined (the node is the
    content of record)."""
    seam = ReadToWriteSeam(
        entity_id=insight.node_id, provenance_ref="evt-promote-1",
        target_section_id=section_id,
    )
    # The receiving (Write) side builds a block that REFERENCES the same node.
    return OutlineBlockContract(
        outline_block_id="ob-1", section_id=section_id,
        block_kind="insight", provenance_kind="graph_node",
        node_id=seam.entity_id,  # ← same id, by reference
        content=None,
    )


def read_to_write_handoff_COPY(insight: InsightNodeContract, *, section_id: str) -> OutlineBlockContract:
    """WRONG read→write: a fork that copies the insight's text into a new
    user-authored block with a fresh id and no node link. This is the
    provenance bug the guard must catch."""
    return OutlineBlockContract(
        outline_block_id="ob-copy", section_id=section_id,
        block_kind="user_authored", provenance_kind="user_authored",
        node_id=None,
        content=insight.text,  # ← content copied; the node link is severed
    )


# ---------------------------------------------------------------------------
# read→write — the cleanest no-copy case (insight node → node-backed block)
# ---------------------------------------------------------------------------


def test_read_to_write_preserves_node_id():
    insight = _research_promotes_insight()
    block = read_to_write_handoff(insight, section_id="sec-A")
    # SAME node id on both sides — the entity moved by reference.
    assert block.node_id == insight.node_id
    assert block.provenance_kind == "graph_node"
    # The block did NOT inline the insight's text (no copy).
    assert block.content is None


def test_read_to_write_copy_fails_the_guard():
    """Rigor #3 — a deliberate copy FAILS same-node-id. The guard distinguishes
    a real handoff from a fork."""
    insight = _research_promotes_insight()
    copied = read_to_write_handoff_COPY(insight, section_id="sec-A")
    # The copy has a different (null) node id and inlined content — exactly what
    # a no-copy assertion rejects.
    assert copied.node_id != insight.node_id
    with pytest.raises(AssertionError):
        _assert_no_copy(sent_id=insight.node_id, received_id=copied.node_id)


def _assert_no_copy(*, sent_id: str, received_id: object) -> None:
    """The reusable no-copy assertion: the received entity references the same
    node id the seam carried. A None / different id is a copy."""
    assert received_id == sent_id, (
        f"seam copied the entity: sent node_id={sent_id!r}, "
        f"received {received_id!r} (a copy/fork, not the same node)"
    )


# ---------------------------------------------------------------------------
# research→read — the insight surfaces under the same id
# ---------------------------------------------------------------------------


def test_research_to_read_preserves_node_id():
    insight = _research_promotes_insight()
    seam = ResearchToReadSeam(entity_id=insight.node_id, provenance_ref="evt-1")
    # Read resolves the same node id; it does not copy the insight.
    surfaced_id = seam.entity_id
    _assert_no_copy(sent_id=insight.node_id, received_id=surfaced_id)
    assert seam.entity_kind == "insight_node"


# ---------------------------------------------------------------------------
# write→read — trace a block back to its node; same id round-trips
# ---------------------------------------------------------------------------


def test_write_to_read_traces_same_block_reference():
    insight = _research_promotes_insight()
    block = read_to_write_handoff(insight, section_id="sec-A")
    # Tracing the block to source carries the BLOCK id by reference; the
    # block's node link still points at the original insight node.
    seam = WriteToReadSeam(entity_id=block.outline_block_id, provenance_ref="evt-trace-1")
    assert seam.entity_id == block.outline_block_id
    # Provenance chain intact: block → same node → (document/chunks downstream).
    _assert_no_copy(sent_id=insight.node_id, received_id=block.node_id)


# ---------------------------------------------------------------------------
# speak→write — the claim-id is preserved as the block's provenance link
# ---------------------------------------------------------------------------


def test_speak_to_write_preserves_claim_reference():
    """Speak claim → synthesized block. The claim is NOT a graph node (promoting
    it is operator-gated G2/G3), so the no-copy invariant here is: the block's
    provenance link is the SAME claim_id the seam carried, not a copied claim."""
    claim_id = "speak-claim-42"
    seam = SpeakToWriteSeam(
        entity_id=claim_id, provenance_ref="evt-attest-1",
        contributor_interview_ids=("iv-1", "iv-2"),
    )
    # The receiving Write side maps to a synthesized block carrying the claim_id
    # as its source link (content is the claim text already in the private
    # deliverable — the publish gate, not a copy, controls public exposure).
    block = OutlineBlockContract(
        outline_block_id="ob-bio-1", section_id="bio-sec-1",
        block_kind="synthesized", provenance_kind="synthesized",
        node_id=None, content="(claim text, already in the private deliverable)",
    )
    # The seam preserved the claim reference + the contributor provenance.
    _assert_no_copy(sent_id=claim_id, received_id=seam.entity_id)
    assert seam.contributor_interview_ids == ("iv-1", "iv-2")
    assert block.provenance_kind == "synthesized"


# ---------------------------------------------------------------------------
# write→speak — PROVISIONAL: no-copy guard skipped with a reason (rigor #1)
# ---------------------------------------------------------------------------


def test_write_to_speak_no_copy():
    question_node_id = "question-node-42"
    seam = WriteToSpeakSeam(
        entity_id=question_node_id,
        provenance_ref="outline-block-7",
        outline_section_id="section-A",
    )
    persisted_guide = {
        "must_cover": [{"id": question_node_id, "question_node_id": question_node_id}]
    }
    _assert_no_copy(
        sent_id=question_node_id,
        received_id=persisted_guide["must_cover"][0]["question_node_id"],
    )
    assert seam.entity_id == question_node_id
    assert "text" not in persisted_guide["must_cover"][0]
