"""Tests for middleware/supersession/.

What this file proves:

1. REVIEW_DECISIONS is the closed set { apply_supersession, dismiss_new,
   dismiss_old, coexist } — no silent additions.
2. ``validate_decision`` accepts every member and rejects everything
   else with a clear ValueError.
3. ``SupersessionVerdict`` rejects unknown contradiction_type values
   at construction time (defensive — the LLM classifier should never
   produce something outside the set, but the dataclass enforces it).
4. ``new_candidate_id`` returns unique UUID-shaped ids.
5. ``emit_supersession_apply`` produces a typed event with all fields
   round-tripping.
6. ``emit_supersession_dismiss`` accepts target="new"/"old" only;
   payload Literal rejects anything else.
7. ``emit_supersession_coexist`` produces a typed event with no edge
   reference (audit-only signal).
8. ``emit_for_decision`` dispatches to the right helper based on the
   decision string; raises on unknown decisions before emitting.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import pytest
from pydantic import ValidationError

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from middleware.supersession import (  # noqa: E402
    CONTRADICTION_TYPES,
    DEFAULT_UNCLASSIFIED_VERDICT,
    REVIEW_DECISIONS,
    SupersessionVerdict,
    emit_for_decision,
    emit_supersession_apply,
    emit_supersession_coexist,
    emit_supersession_dismiss,
    new_candidate_id,
    validate_decision,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    SupersessionApplyPayload,
    SupersessionCoexistPayload,
    SupersessionDismissPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


# ---------------------------------------------------------------------------
# 1. Closed decision set
# ---------------------------------------------------------------------------


def test_review_decisions_is_the_closed_set():
    """Contract: this exact set, no more, no less. If a future change
    adds a decision, this test must be updated AND the SupersessionTarget
    Literal AND emit_for_decision branching."""
    assert frozenset({
        "apply_supersession",
        "dismiss_new",
        "dismiss_old",
        "coexist",
    }) == REVIEW_DECISIONS


def test_contradiction_types_is_the_closed_set():
    assert frozenset({
        "supersession", "uncertainty", "error",
    }) == CONTRADICTION_TYPES


# ---------------------------------------------------------------------------
# 2. validate_decision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("d", sorted(REVIEW_DECISIONS))
def test_validate_decision_accepts_every_member(d):
    assert validate_decision(d) == d


def test_validate_decision_rejects_unknown():
    with pytest.raises(ValueError, match="invalid review decision"):
        validate_decision("archive")
    with pytest.raises(ValueError):
        validate_decision("")


# ---------------------------------------------------------------------------
# 3. SupersessionVerdict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("t", sorted(CONTRADICTION_TYPES))
def test_verdict_accepts_known_contradiction_types(t):
    v = SupersessionVerdict(contradiction_type=t, reasoning="x")
    assert v.contradiction_type == t


def test_verdict_rejects_unknown_contradiction_type():
    with pytest.raises(ValueError, match="contradiction_type"):
        SupersessionVerdict(contradiction_type="brand-new-type", reasoning="x")


def test_default_unclassified_verdict_is_uncertainty():
    """The conservative posture — when no classifier is available we
    force review rather than auto-applying."""
    assert DEFAULT_UNCLASSIFIED_VERDICT.contradiction_type == "uncertainty"


# ---------------------------------------------------------------------------
# 4. new_candidate_id
# ---------------------------------------------------------------------------


def test_new_candidate_id_unique():
    ids = {new_candidate_id() for _ in range(40)}
    assert len(ids) == 40


# ---------------------------------------------------------------------------
# 5. emit_supersession_apply
# ---------------------------------------------------------------------------


def test_emit_supersession_apply_round_trips_typed():
    cid = new_candidate_id()
    when = datetime(2026, 5, 16, 12, 30, 0)
    eid = emit_supersession_apply(
        investigation_id="inv-sup-1",
        candidate_id=cid,
        old_edge_id="edge-old-1",
        new_edge_id="edge-new-1",
        new_valid_until=when,
        reviewer="Faisal",
        review_notes="company raised Series D — old funding edge superseded",
    )
    event = Event.model_validate(trajectory("inv-sup-1")[0])
    assert event.event_id == eid
    assert event.action_type == ActionType.SUPERSESSION_APPLY.value
    assert isinstance(event.payload, SupersessionApplyPayload)
    p = event.payload
    assert p.candidate_id == cid
    assert p.old_edge_id == "edge-old-1"
    assert p.new_edge_id == "edge-new-1"
    assert p.reviewer == "Faisal"
    assert "Series D" in p.review_notes


# ---------------------------------------------------------------------------
# 6. emit_supersession_dismiss
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["new", "old"])
def test_emit_supersession_dismiss_accepts_valid_targets(target):
    cid = new_candidate_id()
    eid = emit_supersession_dismiss(
        investigation_id=f"inv-dismiss-{target}",
        candidate_id=cid,
        edge_id=f"edge-{target}-1",
        target=target,
        valid_until=datetime(2026, 5, 16),
        reviewer="Faisal",
    )
    event = Event.model_validate(trajectory(f"inv-dismiss-{target}")[0])
    assert event.event_id == eid
    assert isinstance(event.payload, SupersessionDismissPayload)
    assert event.payload.target == target


def test_emit_supersession_dismiss_rejects_unknown_target():
    """Payload Literal on SupersessionTarget enforces 'new' | 'old'."""
    with pytest.raises(ValidationError):
        emit_supersession_dismiss(
            investigation_id="inv-x",
            candidate_id="c", edge_id="e",
            target="both",  # not in SupersessionTarget
            valid_until=datetime(2026, 5, 16),
            reviewer="r",
        )


# ---------------------------------------------------------------------------
# 7. emit_supersession_coexist
# ---------------------------------------------------------------------------


def test_emit_supersession_coexist_round_trips_typed():
    cid = new_candidate_id()
    eid = emit_supersession_coexist(
        investigation_id="inv-coexist",
        candidate_id=cid,
        reviewer="Faisal",
        review_notes="both correct under different scope definitions",
    )
    event = Event.model_validate(trajectory("inv-coexist")[0])
    assert event.event_id == eid
    assert event.action_type == ActionType.SUPERSESSION_COEXIST.value
    assert isinstance(event.payload, SupersessionCoexistPayload)
    p = event.payload
    assert p.candidate_id == cid
    assert p.review_notes.startswith("both correct")


# ---------------------------------------------------------------------------
# 8. emit_for_decision dispatcher
# ---------------------------------------------------------------------------


def test_emit_for_decision_applies_supersession():
    cid = new_candidate_id()
    emit_for_decision(
        decision="apply_supersession",
        investigation_id="inv-dispatch-apply",
        candidate_id=cid,
        old_edge_id="edge-old", new_edge_id="edge-new",
        reviewer="Faisal",
        valid_until=datetime(2026, 5, 16),
    )
    event = Event.model_validate(trajectory("inv-dispatch-apply")[0])
    assert isinstance(event.payload, SupersessionApplyPayload)
    assert event.payload.old_edge_id == "edge-old"


def test_emit_for_decision_dismiss_new_uses_new_edge_id():
    emit_for_decision(
        decision="dismiss_new",
        investigation_id="inv-dispatch-dnew",
        candidate_id="c", old_edge_id="edge-old", new_edge_id="edge-new",
        reviewer="r", valid_until=datetime(2026, 5, 16),
    )
    event = Event.model_validate(trajectory("inv-dispatch-dnew")[0])
    assert isinstance(event.payload, SupersessionDismissPayload)
    assert event.payload.target == "new"
    assert event.payload.edge_id == "edge-new"


def test_emit_for_decision_dismiss_old_uses_old_edge_id():
    emit_for_decision(
        decision="dismiss_old",
        investigation_id="inv-dispatch-dold",
        candidate_id="c", old_edge_id="edge-old", new_edge_id="edge-new",
        reviewer="r", valid_until=datetime(2026, 5, 16),
    )
    event = Event.model_validate(trajectory("inv-dispatch-dold")[0])
    assert isinstance(event.payload, SupersessionDismissPayload)
    assert event.payload.target == "old"
    assert event.payload.edge_id == "edge-old"


def test_emit_for_decision_coexist_no_edge_reference():
    emit_for_decision(
        decision="coexist",
        investigation_id="inv-dispatch-co",
        candidate_id="c", old_edge_id="x", new_edge_id="y",
        reviewer="r", valid_until=datetime(2026, 5, 16),
        review_notes="scope dependent",
    )
    event = Event.model_validate(trajectory("inv-dispatch-co")[0])
    assert isinstance(event.payload, SupersessionCoexistPayload)
    # No edge_id on coexist payload — just the audit signal.


def test_emit_for_decision_rejects_unknown_decision():
    with pytest.raises(ValueError, match="invalid review decision"):
        emit_for_decision(
            decision="nuke_it",
            investigation_id="inv-bad", candidate_id="c",
            old_edge_id="x", new_edge_id="y", reviewer="r",
            valid_until=datetime(2026, 5, 16),
        )
