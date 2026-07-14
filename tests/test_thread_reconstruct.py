"""Thread reconstruction unit tests (antiek-unified SPR-06 M1).

Covers the M1 verification gate "Thread reconstructs — correct ordered hops"
for the degenerate (1-workflow) and full-flywheel (N-workflow) cases, plus the
honest-stub behavior for a hop into an unbuilt workflow (intellectual honesty
#1). The no-duplicate guard itself is in ``test_thread_no_duplicate.py``.
"""

from __future__ import annotations

from typing import Any

from substrate.seams.thread import (
    Thread,
    reconstruct_thread,
)


def _ev(event_id: str, action_type: str, node_id: str, emitted_at: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "action_type": action_type,
        "emitted_at": emitted_at,
        "payload": {
            "entity_id": node_id,
            "entity_kind": "insight_node",
            "provenance_ref": f"prov-{event_id}",
            "terminates": True,
        },
    }


def test_degenerate_thread_is_one_hop() -> None:
    thread = reconstruct_thread(
        "node-1", seam_events=[], origin_entity_kind="insight_node"
    )
    assert isinstance(thread, Thread)
    assert thread.is_degenerate
    assert [h.workflow for h in thread.hops] == ["research"]
    assert thread.hops[0].seam_event_id is None  # origin, no seam produced it


def test_full_flywheel_ordered_hops() -> None:
    """research → read → write → read, ordered by emission time. The origin hop
    is the from-workflow of the first seam (research); each seam adds its
    to-workflow hop."""
    node = "node-flywheel"
    events = [
        _ev("e3", "seam.write_to_read", node, "2026-05-25T10:02:00"),
        _ev("e1", "seam.research_to_read", node, "2026-05-25T10:00:00"),
        _ev("e2", "seam.read_to_write", node, "2026-05-25T10:01:00"),
    ]  # deliberately out of emission order — reconstruction must sort
    thread = reconstruct_thread(
        node, seam_events=events, origin_entity_kind="insight_node"
    )
    # origin (research) + read + write + read
    assert [h.workflow for h in thread.hops] == ["research", "read", "write", "read"]
    # The hops in seam order carry their producing seam event id.
    seam_hops = [h for h in thread.hops if h.seam_event_id is not None]
    assert [h.seam_event_id for h in seam_hops] == ["e1", "e2", "e3"]
    assert all(h.entity_id == node for h in thread.hops)


def test_unbuilt_workflow_hop_is_flagged_not_dropped() -> None:
    """Intellectual honesty #1 — a hop into a workflow with no built surface is
    flagged built=False and recorded as an honest stub, never dropped or faked.
    Here we mark 'write' unbuilt and confirm the write hop is present-but-stubbed."""
    node = "node-2"
    events = [
        _ev("e1", "seam.research_to_read", node, "2026-05-25T10:00:00"),
        _ev("e2", "seam.read_to_write", node, "2026-05-25T10:01:00"),
    ]
    thread = reconstruct_thread(
        node,
        seam_events=events,
        origin_entity_kind="insight_node",
        built_workflows=("research", "read", "speak"),  # write NOT built
    )
    write_hops = [h for h in thread.hops if h.workflow == "write"]
    assert write_hops, "the write hop must be present (honest), not dropped"
    assert all(not h.built for h in write_hops)
    assert any(s.workflow == "write" for s in thread.stubs)


def test_committed_write_to_speak_hop_is_not_marked_provisional() -> None:
    """The committed write→speak hop must not render an unfinished warning."""
    node = "node-3"
    events = [
        _ev("e1", "seam.write_to_speak", node, "2026-05-25T10:00:00"),
    ]
    thread = reconstruct_thread(
        node, seam_events=events, origin_entity_kind="question_node"
    )
    speak_hops = [h for h in thread.hops if h.workflow == "speak"]
    assert speak_hops and not speak_hops[0].via_provisional_seam


def test_other_nodes_seam_events_are_ignored() -> None:
    """Only seam events referencing the requested node participate — events for
    a different entity must not leak into this thread."""
    node = "node-A"
    events = [
        _ev("e1", "seam.research_to_read", node, "2026-05-25T10:00:00"),
        _ev("e2", "seam.read_to_write", "node-OTHER", "2026-05-25T10:01:00"),
    ]
    thread = reconstruct_thread(
        node, seam_events=events, origin_entity_kind="insight_node"
    )
    assert all(h.entity_id == node for h in thread.hops)
    # research (origin) + read only — the node-OTHER hop is excluded.
    assert [h.workflow for h in thread.hops] == ["research", "read"]
