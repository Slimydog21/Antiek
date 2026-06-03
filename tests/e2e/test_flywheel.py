"""The end-to-end flywheel test — antiek-unified SPR-08 M1.

The capstone proof that "four products are one product" is mechanically true:
a SINGLE graph entity flows Research → Read → Write → Speak → Read through the
REAL SPR-03 typed seams, and at every hop it is the SAME node id with unbroken
provenance. This is the one test that exercises the *composition* of the seams
rather than any seam in isolation — the failure mode no single-seam test can
catch is "provenance intact per-hop, chain broken across hops" (rigor #2, the
steelman for why this test exists at all).

WHAT IS REAL VS STUB (intellectual honesty #1 — read this before trusting the
green):

  * REAL (the integration substrate this whole spec built):
      - the SPR-03 typed seam contracts (``ResearchToReadSeam`` …
        ``SpeakToReadSeam``) — every hand-off goes through the real frozen
        Pydantic seam model; a copy or a missing field would fail construction.
      - the SPR-01 entity contracts the seams carry (``InsightNodeContract``,
        ``OutlineBlockContract``, ``ServableEntryContract``).
      - the SPR-06 thread reconstruction + no-duplicate assertion
        (``reconstruct_thread`` / ``assert_single_canonical_entity``).
      - the seam-#4 servability gate (``substrate.seams.servability_gate``) —
        the speak→read publish-gate translation, decoupled from substrate.books.

  * STUB (a product's real internals are unbuilt; the test conforms the
    contract and is structured so the real module drops in without a rewrite):
      - Research's ``promote_insight`` — we use a fixture ``InsightNodeContract``
        node, not a live DB promotion. The contract is the same one the real
        promoter conforms to (``tests/test_contracts_conformance.py``).
      - Read's corpus surface (DRW SPR-10 / ``substrate/books/``) — UNMERGED on
        this base. ``import substrate.books`` raises ``ModuleNotFoundError``
        here (verified). So the **served-back-in-Read leg is proven at the
        CONTRACT level**: we assert ``ServableEntryContract.serves_full_text``
        through the seam-#4 ``servability_gate`` (both decoupled from
        substrate.books), and mark plainly that the full live Read-serving leg
        lands when Read's ``substrate/books/`` merges.
      - Write's block repository (Write SPR-03) and Speak's interview/publish
        paths — represented by the contracts the seams carry; no live module.

So the honest claim this test warrants is: *the integration substrate is sound
and conformance-gated; one entity traverses the committed flywheel hops as one
node with unbroken provenance.* NOT "the full product flywheel works end to end"
— most product internals are unbuilt.

HERMETIC: no DB writes, no network, no live LLM. The flywheel is emitted as a
list of seam events in the exact ``substrate.event_log.trajectory`` row shape
(event_id / action_type / emitted_at / payload-with-entity-reference) — the
same shape SPR-06's ``test_thread_no_duplicate`` uses — so a live caller that
passes real ``trajectory()`` rows drops in unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest

# ── REAL integration substrate (SPR-01 / SPR-03 / SPR-06) ────────────────────
from substrate.contracts.interviewer import ConsentContract, InterviewerResultContract
from substrate.contracts.nodes import InsightNodeContract
from substrate.contracts.outline_block import OutlineBlockContract
from substrate.contracts.servable import ServableEntryContract
from substrate.seams import (
    ReadToWriteSeam,
    ResearchToReadSeam,
    SpeakToReadSeam,
    SpeakToWriteSeam,
    WriteToReadSeam,
    servability_gate,
)
from substrate.seams.thread import (
    assert_single_canonical_entity,
    reconstruct_thread,
)

# We reuse the SPR-03 per-seam no-copy assertion DIRECTLY (diligence #4): the
# e2e same-node-id check IS that per-seam guard applied across every hop.
from tests.test_seam_no_copy import _assert_no_copy

# The ONE canonical entity the whole flywheel is about. Content-addressed shape
# (what ``promote_insight`` would mint); fixed here so the test is hermetic.
CANONICAL_INSIGHT = "insight-7f3a9c"
CANONICAL_TEXT = "Werner traded antiques before software."
INVESTIGATION = "inv-werner-1"


# ── Step 0 — Research creates the insight (STUB: fixture node, not a live promote)
def _research_creates_insight() -> InsightNodeContract:
    """Research promotes an insight (DRW SPR-01 ``promote_insight``). STUB: a
    fixture ``InsightNodeContract`` standing in for the live promotion. The
    contract is identical to the one the live promoter conforms to — when
    ``promote_insight`` runs in this test it returns the same node id and this
    fixture is replaced by the real call with no other change."""
    return InsightNodeContract(
        node_id=CANONICAL_INSIGHT,
        text=CANONICAL_TEXT,
        investigation_id=INVESTIGATION,
        confidence="high",
    )


def _seam_event(
    event_id: str,
    action_type: str,
    *,
    entity_id: str,
    entity_kind: str,
    provenance_ref: str,
    emitted_at: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One seam event in the ``trajectory()`` row shape. The entity rides BY
    REFERENCE — there is deliberately NO content field (a content field would
    be a copy, which the thread walk refuses to launder)."""
    payload: dict[str, Any] = {
        "entity_id": entity_id,
        "entity_kind": entity_kind,
        "provenance_ref": provenance_ref,
        "terminates": True,
    }
    if extra:
        payload.update(extra)
    return {
        "event_id": event_id,
        "action_type": action_type,
        "emitted_at": emitted_at,
        "payload": payload,
    }


# ── Fixtures: the committed flywheel, emitted as REAL seam contracts + events ──


@pytest.fixture()
def insight() -> InsightNodeContract:
    return _research_creates_insight()


@pytest.fixture()
def flywheel_seams(insight: InsightNodeContract) -> dict[str, Any]:
    """Drive the entity across the committed seams using the REAL SPR-03 seam
    contracts. Each construction is the load-bearing proof: the seam carries
    ``entity_id`` by reference; a forked/copied id or a missing field would
    fail Pydantic construction here.

    Returns the constructed seam objects + the resolved downstream entities so
    the test can assert the SAME id flows through each.
    """
    # (b) research → read — surface the insight in the reader.
    s_r2read = ResearchToReadSeam(
        entity_id=insight.node_id,
        provenance_ref="evt-promote-1",
    )

    # (c) read → write — drag the insight into an OutlineBlock. The block
    # REFERENCES the same node id; it does not inline the insight text (an
    # inlined copy is the fabricated-citation bug the contract forbids).
    s_read2write = ReadToWriteSeam(
        entity_id=insight.node_id,
        provenance_ref="evt-r2read",
        target_section_id="sec-bio-childhood",
    )
    block = OutlineBlockContract(
        outline_block_id="ob-1",
        section_id=s_read2write.target_section_id,
        block_kind="insight",
        provenance_kind="graph_node",
        node_id=s_read2write.entity_id,  # ← SAME id, by reference
        content=None,
    )

    # (d) a Speak interview corroborates a claim, and speak → write feeds the
    # bio. A Speak biography unit is an interview-attested CLAIM (NOT a graph
    # node — promotion is operator-gated G2/G3), so the seam carries the
    # claim_id. The claim corroborates THIS insight (provenance link), but is a
    # distinct entity of record; the seam moves it by reference, no copy.
    interview = InterviewerResultContract(
        interview_id="iv-werner-1",
        project_id="proj-werner",
        extracted_claim_ids=("speak-claim-werner-antiques",),
        corroboration="multiply_attested",
    )
    claim_id = interview.extracted_claim_ids[0]
    s_speak2write = SpeakToWriteSeam(
        entity_id=claim_id,
        provenance_ref="evt-attest-1",
        contributor_interview_ids=("iv-werner-1",),
    )

    # (e) write → read — trace the published block back to its source in the
    # reading surface. The seam carries the OutlineBlock reference; the
    # receiving (Read) side resolves node → document → chunks (resolution is
    # Read's job, unbuilt here — the source fields stay None at hand-off).
    s_write2read = WriteToReadSeam(
        entity_id=block.outline_block_id,
        provenance_ref="evt-read2write",
    )

    # (e') speak → read — a PUBLISHED biography is served back into the corpus
    # as a ``platform_authored`` / ``speak_derived`` ServableEntry. This is the
    # leg that routes through the seam-#4 publish gate before Read serves full
    # text. The producing (Speak) side computes ``publish_gate_passed``; Read
    # consults the boolean (it never recomputes Speak's gate).
    consent = ConsentContract(
        interview_id="iv-werner-1",
        scopes=("record", "attribute", "publish"),
        verified_before_publish=True,
        right_of_publicity_cleared=True,
        taken_down=False,
    )
    publish_gate_passed = servability_gate.speak_publish_gate_passed(consent)
    served_entry = ServableEntryContract(
        document_id="doc-bio-werner",
        content_class="platform_authored",
        provenance_class="speak_derived",
    )
    s_speak2read = SpeakToReadSeam(
        entity_id=served_entry.document_id,
        provenance_ref="evt-publish-1",
        publish_gate_passed=publish_gate_passed,
    )

    return {
        "insight": insight,
        "block": block,
        "interview": interview,
        "claim_id": claim_id,
        "served_entry": served_entry,
        "consent": consent,
        "publish_gate_passed": publish_gate_passed,
        "seams": {
            "research_to_read": s_r2read,
            "read_to_write": s_read2write,
            "speak_to_write": s_speak2write,
            "write_to_read": s_write2read,
            "speak_to_read": s_speak2read,
        },
    }


@pytest.fixture()
def flywheel_events(insight: InsightNodeContract) -> list[dict[str, Any]]:
    """The insight's cross-workflow trajectory as ``trajectory()`` rows. The
    insight-node thread is research → read → write → read; every hop references
    CANONICAL_INSIGHT, chained by ``provenance_ref`` into one lineage. (The
    Speak→Write claim is a DIFFERENT entity of record — its own thread — covered
    by ``test_speak_claim_leg_is_its_own_thread`` below.)"""
    return [
        _seam_event(
            "evt-r2read", "seam.research_to_read",
            entity_id=insight.node_id, entity_kind="insight_node",
            provenance_ref="evt-promote-1", emitted_at="2026-05-25T10:00:00",
        ),
        _seam_event(
            "evt-read2write", "seam.read_to_write",
            entity_id=insight.node_id, entity_kind="insight_node",
            provenance_ref="evt-r2read", emitted_at="2026-05-25T10:01:00",
            extra={"target_section_id": "sec-bio-childhood"},
        ),
        _seam_event(
            "evt-write2read", "seam.write_to_read",
            entity_id=insight.node_id, entity_kind="insight_node",
            provenance_ref="evt-read2write", emitted_at="2026-05-25T10:02:00",
        ),
    ]


# ── M1 acceptance — one entity, full cycle, same node id, gates fire ──────────


def test_one_entity_traverses_committed_flywheel_via_real_seams(
    flywheel_seams: dict[str, Any],
) -> None:
    """Acceptance: one entity traverses the committed flywheel hops via the REAL
    SPR-03 seams, and the SAME node id flows through each hop that carries it.

    The insight-node legs (research→read, read→write, write→read) all reference
    the one ``CANONICAL_INSIGHT``. The speak legs carry their own entities of
    record (a claim, a servable document) by reference — the flywheel is one
    entity *per thread*; the insight thread is the spine."""
    s = flywheel_seams["seams"]
    insight = flywheel_seams["insight"]
    block = flywheel_seams["block"]

    # research → read carries the insight by reference.
    assert s["research_to_read"].entity_id == insight.node_id
    assert s["research_to_read"].entity_kind == "insight_node"
    assert s["research_to_read"].from_workflow == "research"
    assert s["research_to_read"].to_workflow == "read"

    # read → write: the block is node-backed by the SAME id (no copy).
    assert s["read_to_write"].entity_id == insight.node_id
    assert block.node_id == insight.node_id
    assert block.content is None  # the node is the content of record, not inlined
    _assert_no_copy(sent_id=insight.node_id, received_id=block.node_id)

    # write → read: the trace carries the block reference.
    assert s["write_to_read"].entity_id == block.outline_block_id
    assert s["write_to_read"].from_workflow == "write"
    assert s["write_to_read"].to_workflow == "read"


def test_provenance_chain_unbroken_end_to_end(
    flywheel_events: list[dict[str, Any]],
) -> None:
    """Acceptance: the provenance chain is unbroken end-to-end. The thread walk
    reconstructs the insight's trajectory by FOLLOWING the provenance lineage
    (each seam's ``provenance_ref`` points at the prior hop's event id) — not by
    filtering on id equality (which would silently drop a fork). Every hop
    chains to the one before it; no hop is orphaned."""
    thread = reconstruct_thread(
        CANONICAL_INSIGHT,
        seam_events=flywheel_events,
        origin_entity_kind="insight_node",
    )
    # origin (research) + read + write + read.
    assert not thread.is_degenerate
    assert thread.workflows == ("research", "read", "write")
    # The chain is unbroken: every non-origin hop names the seam event that
    # produced it, and that event's provenance_ref points back into the lineage.
    event_ids = {e["event_id"] for e in flywheel_events}
    provrefs = {e["payload"]["provenance_ref"] for e in flywheel_events}
    # the very first seam's provenance_ref is the origin promote event; every
    # subsequent provenance_ref is a prior seam event id → the chain links up.
    chained = provrefs & (event_ids | {"evt-promote-1"})
    assert chained == provrefs, (
        "a seam's provenance_ref does not resolve to a prior hop — the "
        "provenance chain is broken"
    )


def test_same_node_id_at_every_hop(
    flywheel_events: list[dict[str, Any]],
) -> None:
    """Acceptance: the SAME node id at every hop (composes SPR-06's
    no-duplicate guarantee). This is the load-bearing assertion — the thing
    that makes "one entity everywhere" mechanically true."""
    thread = reconstruct_thread(
        CANONICAL_INSIGHT,
        seam_events=flywheel_events,
        origin_entity_kind="insight_node",
    )
    # Per-hop: each references the canonical id (SPR-03 guard, applied to all).
    for hop in thread.hops:
        _assert_no_copy(sent_id=CANONICAL_INSIGHT, received_id=hop.entity_id)
    # Packaged thread-level assertion (SPR-06 M4).
    assert_single_canonical_entity(thread)


def test_platform_authored_gate_fires_speak_derived_serves_only_after_publish_gate(
    flywheel_seams: dict[str, Any],
) -> None:
    """Acceptance: the platform_authored gate fires — a speak-derived doc only
    serves full text AFTER the publish gate passes (seam #4). This is the
    served-back-in-Read leg, proven at the CONTRACT level via the seam-#4
    ``servability_gate`` (decoupled from substrate.books, which is UNMERGED on
    this base — the full live Read-serving leg lands when Read's
    ``substrate/books/`` merges; honesty #1).

    The gate decision is deny-by-default and routed through the seam, not
    Read's internals."""
    served_entry = flywheel_seams["served_entry"]
    consent = flywheel_seams["consent"]
    s_speak2read = flywheel_seams["seams"]["speak_to_read"]

    # The producing (Speak) side computed publish_gate_passed from consent.
    assert s_speak2read.publish_gate_passed is True
    assert servability_gate.speak_publish_gate_passed(consent) is True

    # With the gate passed, the speak_derived entry serves full text.
    assert servability_gate.serves_full_text(
        served_entry, publish_gate_passed=s_speak2read.publish_gate_passed
    ) is True

    # NEGATIVE (the gate must MATTER): a speak_derived doc whose publish gate
    # did NOT pass is NOT served full text. A gate that served regardless would
    # guard nothing.
    assert servability_gate.serves_full_text(
        served_entry, publish_gate_passed=False
    ) is False
    # And the stamped entry's own derivation agrees (deny-by-default).
    gated = servability_gate.gate_speak_derived_entry(
        served_entry, publish_gate_passed=False
    )
    assert gated.serves_full_text is False


def test_speak_claim_leg_is_its_own_thread_by_reference(
    flywheel_seams: dict[str, Any],
) -> None:
    """The speak → write leg moves a CLAIM (not a graph node — promotion is
    operator-gated G2/G3). It is its own entity of record; the seam carries the
    claim id by reference, and its single-hop thread holds one canonical id (no
    copy). This is the honesty nuance from the seam contract, exercised."""
    claim_id = flywheel_seams["claim_id"]
    s_speak2write = flywheel_seams["seams"]["speak_to_write"]
    assert s_speak2write.entity_id == claim_id
    assert s_speak2write.entity_kind == "speak_claim"

    claim_events = [
        _seam_event(
            "evt-speak2write", "seam.speak_to_write",
            entity_id=claim_id, entity_kind="speak_claim",
            provenance_ref="evt-attest-1", emitted_at="2026-05-25T09:00:00",
            extra={"contributor_interview_ids": ["iv-werner-1"]},
        ),
    ]
    thread = reconstruct_thread(
        claim_id, seam_events=claim_events, origin_entity_kind="speak_claim",
    )
    assert thread.canonical_entity_kind == "speak_claim"
    assert thread.workflows == ("speak", "write")
    assert_single_canonical_entity(thread)


# ── Rigor #3 — inject a copy at one hop; the same-node-id assertion FAILS ─────


def test_injected_entity_copy_fails_the_flywheel_guard(
    flywheel_events: list[dict[str, Any]],
) -> None:
    """The deciding rigor: inject an entity COPY at one hop (the write→read hop
    forks the node id) and watch the same-node-id assertion FAIL. A flywheel
    guard that passed whether or not the entity was copied would prove nothing
    — this is the negative that gives the positive its meaning."""
    corrupted = [dict(e, payload=dict(e["payload"])) for e in flywheel_events]
    # Fork the entity on the last hop: a fresh, divergent id (the provenance
    # bug a buggy seam that copied instead of referenced would produce).
    corrupted[-1]["payload"]["entity_id"] = CANONICAL_INSIGHT + "-COPY"

    thread = reconstruct_thread(
        CANONICAL_INSIGHT,
        seam_events=corrupted,
        origin_entity_kind="insight_node",
    )
    # The forked hop is surfaced WITH its wrong id (not silently dropped) ...
    forked = [h for h in thread.hops if h.entity_id != CANONICAL_INSIGHT]
    assert forked, "the injected copy must surface as a forked hop, not vanish"
    # ... so the load-bearing assertion rejects the thread.
    with pytest.raises(AssertionError, match="copy"):
        assert_single_canonical_entity(thread)


def test_injected_inline_content_copy_is_refused(
    flywheel_events: list[dict[str, Any]],
) -> None:
    """A seam event that inlines the entity's CONTENT (not just its id) is a
    fork by construction — seam payloads deliberately carry no content field.
    The thread walk refuses to launder it, raising rather than weaving it in."""
    corrupted = [dict(e, payload=dict(e["payload"])) for e in flywheel_events]
    corrupted[1]["payload"]["content"] = CANONICAL_TEXT  # inline the insight text
    with pytest.raises(ValueError, match="copied entity"):
        reconstruct_thread(
            CANONICAL_INSIGHT,
            seam_events=corrupted,
            origin_entity_kind="insight_node",
        )


# ── Structured so a real product module drops in without rewriting the test ───


def test_real_module_drop_in_contract_is_stable() -> None:
    """Acceptance: the test is structured so a real product module drops in
    without a rewrite. The drop-in contract is: a real ``promote_insight``
    returns an object satisfying ``InsightNodeContract`` (same node_id); a real
    Write block repository returns an ``OutlineBlockContract``; a real Read
    serving layer consults ``ServableEntryContract.serves_full_text`` via the
    same ``servability_gate``. We assert the shapes the real modules must honor
    are exactly the ones this test composes — so swapping a fixture for a live
    call changes the call, not the assertions."""
    # the insight contract the real promoter must satisfy
    node = _research_creates_insight()
    assert isinstance(node, InsightNodeContract)
    # the block contract the real Write repo must produce (node-backed)
    block = OutlineBlockContract(
        outline_block_id="ob-x", section_id="sec-x",
        block_kind="insight", provenance_kind="graph_node",
        node_id=node.node_id,
    )
    assert block.node_id == node.node_id
    # the servable contract the real Read serve.py must consult
    entry = ServableEntryContract(
        document_id="doc-x", content_class="platform_authored",
        provenance_class="operator_authored",
    )
    # operator_authored is auto-servable (no Write-output regression).
    assert servability_gate.serves_full_text(entry, publish_gate_passed=False) is True
