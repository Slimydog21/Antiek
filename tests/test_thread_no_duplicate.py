"""The thread-level no-duplicate-entity guard (antiek-unified SPR-06 M4).

This is the LOAD-BEARING gate for cross-workflow navigation. The breadcrumb in
SPR-06 lets the operator follow one entity across the four workflows (Speak →
insight → Write → Read). That navigation is only trustworthy if the entity is
*genuinely one entity* — the same node id at every hop. If any workflow holds a
copy/fork, the breadcrumb asserts a continuity the data doesn't support: it
lies. So this test is the breadcrumb's WARRANT — if it can't pass, the
breadcrumb must not ship (defensibility #5).

It COMPOSES the SPR-03 no-copy seam guarantee
(``tests/test_seam_no_copy.py::_assert_no_copy``, which proves each individual
seam moves the entity by reference) up to the *whole trajectory*: every hop a
reconstructed thread carries references the same canonical node id. The deciding
rigor (rigor #3): a fixture that deliberately COPIES the entity FAILS the guard.
A guard that passed whether or not the entity was copied would prove nothing.

The fixture spans the real flywheel depth available (rigor #3): the full
research → read → write → read trajectory, not just two hops, plus the
Speak-claim → Write biography handoff. SPR-08's e2e flywheel test composes this
assertion end-to-end.
"""

from __future__ import annotations

from typing import Any

import pytest

# We reuse the SPR-03 no-copy seam assertion DIRECTLY (diligence #4 / rigor #3):
# the thread-level guard is that same per-hop assertion, applied to every hop.
from tests.test_seam_no_copy import _assert_no_copy
from substrate.seams.thread import (
    assert_single_canonical_entity,
    reconstruct_thread,
)


# ---------------------------------------------------------------------------
# Fixtures: a small flywheel emitted as SPR-03 seam events. These mirror the
# real event-log shape (``substrate.event_log.trajectory`` rows): event_id,
# action_type, emitted_at, payload-with-entity-reference. The CORRECT fixtures
# carry the entity BY REFERENCE (same id, no inlined content). The COPY fixture
# forks it — and must fail the guard.
# ---------------------------------------------------------------------------

# The one canonical node id the whole flywheel is about.
CANONICAL_INSIGHT = "insight-7f3a9c"


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
    """Build one seam event in the trajectory() row shape. The entity travels
    by reference: there is NO content field (a content field would be a copy)."""
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


def _full_flywheel_events_by_reference() -> list[dict[str, Any]]:
    """The full flywheel for ONE insight, every hop carrying the SAME node id.

    research → read (surface the insight)
    read → write    (drag the insight into an outline)
    write → read    (trace the block back to its source)

    Every seam event references CANONICAL_INSIGHT; none inlines its content.
    The seams chain by ``provenance_ref`` — each points at the prior hop's event
    id — so they form one trajectory lineage (the thread walk follows it). This
    is what makes a forked copy (same lineage, divergent id) impossible to
    silently drop: it stays in the lineage and surfaces with its wrong id."""
    return [
        _seam_event(
            "evt-r2read", "seam.research_to_read",
            entity_id=CANONICAL_INSIGHT, entity_kind="insight_node",
            provenance_ref="evt-promote-1", emitted_at="2026-05-25T10:00:00",
        ),
        _seam_event(
            "evt-read2write", "seam.read_to_write",
            entity_id=CANONICAL_INSIGHT, entity_kind="insight_node",
            provenance_ref="evt-r2read", emitted_at="2026-05-25T10:01:00",
            extra={"target_section_id": "sec-A"},
        ),
        _seam_event(
            "evt-write2read", "seam.write_to_read",
            entity_id=CANONICAL_INSIGHT, entity_kind="insight_node",
            provenance_ref="evt-read2write", emitted_at="2026-05-25T10:02:00",
        ),
    ]


def _copy_corrupted_events() -> list[dict[str, Any]]:
    """Same flywheel, but the write→read hop holds a COPY: a forked node id with
    a fresh id (the provenance bug). The thread reconstruction will pick up the
    canonical-id hops, but the corrupted hop references a DIFFERENT id — which
    the no-duplicate guard must reject."""
    events = _full_flywheel_events_by_reference()
    # Corrupt the LAST hop: it now references a forked copy, not the one node.
    events[-1]["payload"]["entity_id"] = "insight-7f3a9c-COPY"
    return events


# ---------------------------------------------------------------------------
# M4 acceptance: reconstruct a multi-workflow thread, assert single canonical id.
# ---------------------------------------------------------------------------


def test_full_flywheel_thread_single_canonical_node_id() -> None:
    """A thread crossing N workflows references the SAME node id at every hop.

    This is the positive case: the by-reference flywheel reconstructs a thread
    whose every hop carries CANONICAL_INSIGHT, and the load-bearing assertion
    passes."""
    thread = reconstruct_thread(
        CANONICAL_INSIGHT,
        seam_events=_full_flywheel_events_by_reference(),
        origin_entity_kind="insight_node",
    )
    # The trajectory touched more than one workflow (not degenerate).
    assert not thread.is_degenerate
    # research (origin) → read → write → read.
    assert thread.workflows == ("research", "read", "write")
    # Every hop references the one canonical node id — composes the SPR-03
    # per-seam no-copy guarantee across the whole thread.
    for hop in thread.hops:
        _assert_no_copy(sent_id=CANONICAL_INSIGHT, received_id=hop.entity_id)
    # And the packaged thread-level assertion passes.
    assert_single_canonical_entity(thread)


def test_deliberate_copy_fixture_fails_the_guard() -> None:
    """Rigor #3 — a deliberately COPIED entity FAILS the no-duplicate guard.

    If this didn't fail, the guard would prove nothing. The corrupted fixture
    forks the entity on the last hop; reconstruction surfaces that forked id,
    and ``assert_single_canonical_entity`` rejects it."""
    thread = reconstruct_thread(
        # We still ask for the canonical thread; the corrupted hop references a
        # fork. (Real-world: a buggy seam that copied instead of referencing.)
        CANONICAL_INSIGHT,
        seam_events=_copy_corrupted_events(),
        origin_entity_kind="insight_node",
    )
    # The corrupted hop is present with the WRONG id, so the thread-level guard
    # must raise — the breadcrumb over this thread would lie.
    with pytest.raises(AssertionError):
        assert_single_canonical_entity(thread)


def test_copy_guard_composes_spr03_assert_no_copy() -> None:
    """Defensibility #5 — the thread guard IS the SPR-03 per-seam guard applied
    across hops. Prove the composition directly: a forked id fails the very
    same ``_assert_no_copy`` the seams use."""
    forked_id = "insight-7f3a9c-COPY"
    # The SPR-03 seam-level guard rejects the fork on a single hop ...
    with pytest.raises(AssertionError):
        _assert_no_copy(sent_id=CANONICAL_INSIGHT, received_id=forked_id)
    # ... and the thread-level guard is that same rejection over the trajectory.
    thread = reconstruct_thread(
        CANONICAL_INSIGHT,
        seam_events=_copy_corrupted_events(),
        origin_entity_kind="insight_node",
    )
    forked_hops = [h for h in thread.hops if h.entity_id != CANONICAL_INSIGHT]
    assert forked_hops, "the corrupted fixture must surface a forked hop"
    assert all(h.entity_id == forked_id for h in forked_hops)


# ---------------------------------------------------------------------------
# An inlined-content seam event is itself a copy — refuse to launder it.
# ---------------------------------------------------------------------------


def test_inlined_content_seam_event_is_rejected_as_a_copy() -> None:
    """A seam event that carries the entity's CONTENT (not just its id) is a
    fork by construction — seam payloads deliberately have no content field
    (substrate/schemas/events.py). The thread walk refuses to weave such an
    event in, raising rather than silently laundering the copy."""
    events = _full_flywheel_events_by_reference()
    # Inline the insight text on a hop — the copy signature.
    events[1]["payload"]["content"] = "Werner traded antiques before software."
    with pytest.raises(ValueError, match="copied entity"):
        reconstruct_thread(
            CANONICAL_INSIGHT,
            seam_events=events,
            origin_entity_kind="insight_node",
        )


# ---------------------------------------------------------------------------
# Degenerate + speak-claim coverage (acceptance: 1-workflow and N-workflow).
# ---------------------------------------------------------------------------


def test_degenerate_single_workflow_thread() -> None:
    """An entity touched by exactly ONE workflow (no seam fired) is a valid
    degenerate thread — one hop, the canonical id, no fork."""
    thread = reconstruct_thread(
        CANONICAL_INSIGHT,
        seam_events=[],  # no seam handed it anywhere
        origin_entity_kind="insight_node",
    )
    assert thread.is_degenerate
    assert len(thread.hops) == 1
    assert thread.hops[0].entity_id == CANONICAL_INSIGHT
    assert_single_canonical_entity(thread)


def test_speak_claim_thread_preserves_claim_reference() -> None:
    """The Speak→Write biography handoff: a speak_claim (NOT a graph node;
    promoting it is operator-gated G2/G3) is carried by claim id. The thread is
    *about the claim id*, and the guard holds for it too — the claim reference
    is preserved, not copied (composes test_seam_no_copy's claim case)."""
    claim_id = "speak-claim-42"
    events = [
        _seam_event(
            "evt-speak2write", "seam.speak_to_write",
            entity_id=claim_id, entity_kind="speak_claim",
            provenance_ref="evt-attest-1", emitted_at="2026-05-25T09:00:00",
            extra={"contributor_interview_ids": ["iv-1", "iv-2"]},
        ),
    ]
    thread = reconstruct_thread(
        claim_id, seam_events=events, origin_entity_kind="speak_claim",
    )
    assert thread.canonical_entity_kind == "speak_claim"
    assert thread.workflows == ("speak", "write")
    for hop in thread.hops:
        _assert_no_copy(sent_id=claim_id, received_id=hop.entity_id)
    assert_single_canonical_entity(thread)
