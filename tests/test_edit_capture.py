"""Tests for edit + authoring-trajectory capture (specs/write/ SPR-02).

Coverage maps to the milestones + rigor #3 edge cases:

M1 edit-pair capture — granular before/after events at the right
   granularity; locator round-trips.
M2 trajectory reconstruction — block-selection → edits → final ordered;
   spans sessions (stitches by deliverable_id); reverted edits captured
   but excluded from signal; dedupes by event_id; manual-first-write
   (edits with no prior draft) reconstructs fine.
M3 harvest — reuses the existing HarvestedTrajectory shape; reward None.
M4 training gate — the training-bound harvest is refused pre-unlock; the
   storage-harvest is unaffected by the gate.

The "capture is not training" invariant is the spine: a maintainer must
be able to confirm no pre-gate training path exists.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.edit import (
    AuthoringHarvestGated,
    EditLocator,
    EditPair,
    capture_edit,
    harvest_authoring_for_training,
    harvest_authoring_trajectory,
    load_authoring_trajectory,
    reconstruct_from_events,
)
from substrate.loop_3.trajectory_harvest import HarvestedTrajectory


@pytest.fixture()
def events_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    # Ensure the gate is closed for the gate tests unless explicitly opened.
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    return tmp_path


# ── M1 — edit-pair capture ─────────────────────────────────────────


def test_capture_edit_emits_structured_event(events_env):
    loc = EditLocator(
        deliverable_id="dlv-1", section_id="sec-1",
        outline_block_id="oblk-1", paragraph_index=2,
    )
    eid = capture_edit(
        locator=loc, edit_kind="replace", granularity="paragraph",
        before_text="the cat sat", after_text="the cat sat quietly",
    )
    assert eid is not None
    events = load_authoring_trajectory("dlv-1").steps
    assert len(events) == 1
    pair = EditPair.from_event({
        "event_id": eid, "action_type": "edit.captured",
        "payload": events[0].payload, "emitted_at": events[0].emitted_at,
    })
    assert pair.edit_kind == "replace"
    assert pair.granularity == "paragraph"
    assert pair.before_text == "the cat sat"
    assert pair.after_text == "the cat sat quietly"
    assert pair.locator.paragraph_index == 2


def test_locator_key_is_stable():
    a = EditLocator("d", "s", "b", 1, 0)
    b = EditLocator("d", "s", "b", 1, 0)
    assert a.key() == b.key()
    assert EditLocator("d", "s").key() != a.key()


# ── M2 — trajectory reconstruction ─────────────────────────────────


def _ev(action_type, payload, eid, ts):
    return {"action_type": action_type, "payload": payload,
            "event_id": eid, "emitted_at": ts}


def test_reconstruct_orders_and_scopes_by_deliverable():
    events = [
        _ev("outline_block.placed", {"deliverable_id": "d1", "outline_block_id": "b1"}, "e1", "2026-05-25T10:00:00Z"),
        _ev("edit.captured", {"deliverable_id": "d1", "edit_kind": "insert"}, "e2", "2026-05-25T10:01:00Z"),
        _ev("edit.captured", {"deliverable_id": "d2", "edit_kind": "insert"}, "e3", "2026-05-25T10:02:00Z"),  # other deliverable
        _ev("dispatch.call", {"deliverable_id": "d1"}, "e4", "2026-05-25T10:03:00Z"),  # not an authoring step
    ]
    traj = reconstruct_from_events(events, "d1")
    assert [s.kind for s in traj.steps] == ["block_selection", "edit"]
    assert all(s.payload.get("deliverable_id") == "d1" for s in traj.steps)


def test_reverted_edits_excluded_from_signal():
    events = [
        _ev("edit.captured", {"deliverable_id": "d1", "edit_kind": "replace", "reverted": False}, "e1", "t1"),
        _ev("edit.captured", {"deliverable_id": "d1", "edit_kind": "replace", "reverted": True}, "e2", "t2"),
    ]
    traj = reconstruct_from_events(events, "d1")
    assert len(traj.steps) == 2          # both captured (the chain is signal)
    assert len(traj.signal_steps) == 1   # but the revert is not endorsement
    assert traj.signal_steps[0].event_id == "e1"


def test_reconstruct_dedupes_by_event_id():
    events = [
        _ev("edit.captured", {"deliverable_id": "d1"}, "e1", "t1"),
        _ev("edit.captured", {"deliverable_id": "d1"}, "e1", "t1"),  # duplicate
    ]
    traj = reconstruct_from_events(events, "d1")
    assert len(traj.steps) == 1


def test_manual_first_write_has_no_prior_draft():
    # An edit with no preceding block-selection/draft still reconstructs.
    events = [_ev("edit.captured", {"deliverable_id": "d1", "edit_kind": "insert"}, "e1", "t1")]
    traj = reconstruct_from_events(events, "d1")
    assert len(traj.steps) == 1
    assert traj.steps[0].kind == "edit"


def test_trajectory_stitches_across_sessions(events_env):
    # Two capture calls under different investigation ids, same deliverable.
    capture_edit(
        locator=EditLocator(deliverable_id="dlv-X", section_id="s1"),
        edit_kind="insert", granularity="block", after_text="first",
        investigation_id="session-a",
    )
    capture_edit(
        locator=EditLocator(deliverable_id="dlv-X", section_id="s1"),
        edit_kind="replace", granularity="paragraph", after_text="second",
        investigation_id="session-b",
    )
    traj = load_authoring_trajectory(
        "dlv-X", investigation_ids=["session-a", "session-b"],
    )
    assert len(traj.edit_steps) == 2


# ── M3 — harvest format ────────────────────────────────────────────


def test_harvest_reuses_existing_shape_with_reward_none():
    events = [
        _ev("outline_block.placed", {"deliverable_id": "d1", "outline_block_id": "b1"}, "e1", "t1"),
        _ev("edit.captured", {"deliverable_id": "d1", "edit_kind": "replace",
                              "before_text": "x", "after_text": "y", "granularity": "sentence"}, "e2", "t2"),
    ]
    traj = reconstruct_from_events(events, "d1")
    harvested = harvest_authoring_trajectory(traj)
    assert isinstance(harvested, HarvestedTrajectory)  # not a parallel format
    assert harvested.investigation_id == "d1"
    assert len(harvested.triples) == 2
    assert all(t["reward"] is None for t in harvested.triples)
    # Edit triple surfaces before/after for the (gated) reward model.
    edit_triple = harvested.triples[1]
    assert edit_triple["info"]["before_text"] == "x"
    assert edit_triple["info"]["after_text"] == "y"
    assert harvested.metadata["reward_status"] == "none_pre_unlock"


def test_storage_harvest_unaffected_by_gate(events_env):
    """Capture + storage-harvest run with the gate CLOSED."""
    assert os.environ.get("ANTIEK_LOOP3_UNLOCKED") != "1"
    traj = reconstruct_from_events(
        [_ev("edit.captured", {"deliverable_id": "d1"}, "e1", "t1")], "d1",
    )
    harvested = harvest_authoring_trajectory(traj)  # must NOT raise
    assert len(harvested.triples) == 1


# ── M4 — training gate ─────────────────────────────────────────────


def test_training_harvest_refused_pre_unlock(events_env):
    traj = reconstruct_from_events(
        [_ev("edit.captured", {"deliverable_id": "d1"}, "e1", "t1")], "d1",
    )
    with pytest.raises(AuthoringHarvestGated, match="ratif"):
        harvest_authoring_for_training(traj)


def test_training_harvest_allowed_when_unlocked(events_env, monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")
    traj = reconstruct_from_events(
        [_ev("edit.captured", {"deliverable_id": "d1"}, "e1", "t1")], "d1",
    )
    harvested = harvest_authoring_for_training(traj)
    # Even unlocked, reward stays None — reward is the rubric_verifier's job.
    assert all(t["reward"] is None for t in harvested.triples)


def test_no_trainer_import_in_capture_or_storage_harvest():
    """Structural guard: the capture + storage-harvest modules must not
    *import* sft_runner / rubric_verifier (no pre-gate training path).

    AST-level so a prose mention in a docstring (explaining that they are
    deliberately NOT imported) does not falsely trip the guard."""
    import ast

    import substrate.edit.edit_pair as ep
    import substrate.edit.harvest_authoring as ha

    forbidden = ("sft_runner", "rubric_verifier")
    for mod in (ep, ha):
        tree = ast.parse(open(mod.__file__).read())
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
                imported.extend(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        for token in forbidden:
            assert not any(token in name for name in imported), (
                f"{mod.__name__} must not import {token} — there is no "
                "pre-gate training path"
            )
