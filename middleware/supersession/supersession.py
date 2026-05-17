"""Supersession review queue (Researchmaxx spec §D.2; architecture_notes §4).

When the extractor produces an edge that contradicts an existing edge,
the supersession layer DOES NOT auto-apply supersession. It writes a
candidate row for human review. The reviewer chooses one of four
decisions; this module enforces the closed set:

| decision           | edge effect                                       |
|--------------------|---------------------------------------------------|
| apply_supersession | old.valid_until=now, old.superseded_by=new        |
| dismiss_new        | new.valid_until=now (the new edge was wrong)      |
| dismiss_old        | old.valid_until=now (the old edge was wrong)      |
| coexist            | no edge change — both remain valid                |

The spec is explicit that automated supersession is the wrong posture
for investment-relevant claims because the definitional questions are
subtle. This module enforces that posture: **contradictions become
tasks, not actions**.

What landed in Sprint 2 Day 3-4 (this migration):

- The pure validators: ``REVIEW_DECISIONS`` set, ``validate_decision``.
- The ``SupersessionVerdict`` dataclass for the LLM classifier output.
- The 3 emit helpers: ``emit_supersession_apply``,
  ``emit_supersession_dismiss``, ``emit_supersession_coexist``.

DEFERRED until init_db migrates: the DB-touching detector
(``detect_for_edge``, ``detect_recent``), the LLM classifier (which
will route through ``substrate/dispatch/`` instead of OpenRouter
directly), and the ``apply_review`` write path.
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    from ...event_log import emit_typed
    from ...schemas import (
        SupersessionApplyPayload,
        SupersessionCoexistPayload,
        SupersessionDismissPayload,
        SupersessionTarget,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        SupersessionApplyPayload,
        SupersessionCoexistPayload,
        SupersessionDismissPayload,
        SupersessionTarget,
    )


# Closed set of valid reviewer decisions. The schema-level Literal on
# each emit helper enforces this at write time; ``validate_decision``
# enforces it at validation time for ``apply_review`` calls that
# haven't yet reached the emit layer.
REVIEW_DECISIONS: frozenset[str] = frozenset({
    "apply_supersession",
    "dismiss_new",
    "dismiss_old",
    "coexist",
})

# Closed set of contradiction-type classifier outputs from the LLM
# triage step. Conservative default is "uncertainty" — forces human
# review rather than auto-applying.
CONTRADICTION_TYPES: frozenset[str] = frozenset({
    "supersession",
    "uncertainty",
    "error",
})


# ---------------------------------------------------------------------------
# Pure types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupersessionVerdict:
    """Output of the contradiction classifier — what the LLM (or the
    rule-based fallback) thinks the contradiction type is. Stored on
    ``supersession_candidates.contradiction_type`` and used by the
    review UI to highlight likely-supersession candidates."""

    contradiction_type: str  # one of CONTRADICTION_TYPES
    reasoning: str

    def __post_init__(self) -> None:
        if self.contradiction_type not in CONTRADICTION_TYPES:
            raise ValueError(
                f"contradiction_type must be one of {sorted(CONTRADICTION_TYPES)}, "
                f"got {self.contradiction_type!r}"
            )


def validate_decision(decision: str) -> str:
    """Confirm ``decision`` is one of the valid reviewer choices.
    Returns the decision unchanged on success; raises ValueError
    otherwise. Used by ``apply_review`` callers before any DB write."""
    if decision not in REVIEW_DECISIONS:
        raise ValueError(
            f"invalid review decision {decision!r}; expected one of "
            f"{sorted(REVIEW_DECISIONS)}"
        )
    return decision


def new_candidate_id() -> str:
    """Allocate a fresh candidate_id (uuid4 — Researchmaxx-compatible)."""
    return str(uuid.uuid4())


# Conservative default when the LLM classifier is unavailable. Forces
# the candidate into the review queue without making any claim about
# whether it's a supersession or not.
DEFAULT_UNCLASSIFIED_VERDICT = SupersessionVerdict(
    contradiction_type="uncertainty",
    reasoning="classifier unavailable; defaulting to uncertainty",
)


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------


def emit_supersession_apply(
    *,
    investigation_id: str,
    candidate_id: str,
    old_edge_id: str,
    new_edge_id: str,
    new_valid_until: datetime,
    reviewer: str,
    review_notes: str = "",
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Emit a SUPERSESSION_APPLY event. Call AFTER the edges table
    commit so we never advertise an apply that didn't write."""
    return emit_typed(
        investigation_id,
        SupersessionApplyPayload(
            candidate_id=candidate_id,
            old_edge_id=old_edge_id,
            new_edge_id=new_edge_id,
            new_valid_until=new_valid_until,
            reviewer=reviewer,
            review_notes=review_notes,
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",  # supersession is part of the tier/attribution layer
    )


def emit_supersession_dismiss(
    *,
    investigation_id: str,
    candidate_id: str,
    edge_id: str,
    target: str,  # "new" | "old"
    valid_until: datetime,
    reviewer: str,
    review_notes: str = "",
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Emit a SUPERSESSION_DISMISS event. ``target`` is enforced by the
    Pydantic Literal on the payload — pass "new" if dismissing the new
    edge, "old" if dismissing the old edge."""
    return emit_typed(
        investigation_id,
        SupersessionDismissPayload(
            candidate_id=candidate_id,
            edge_id=edge_id,
            target=target,  # type: ignore[arg-type]
            valid_until=valid_until,
            reviewer=reviewer,
            review_notes=review_notes,
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",
    )


def emit_supersession_coexist(
    *,
    investigation_id: str,
    candidate_id: str,
    reviewer: str,
    review_notes: str = "",
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Emit a SUPERSESSION_COEXIST event. No edge mutation occurs;
    this is the audit signal that the reviewer chose to keep both
    edges active."""
    return emit_typed(
        investigation_id,
        SupersessionCoexistPayload(
            candidate_id=candidate_id,
            reviewer=reviewer,
            review_notes=review_notes,
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",
    )


def emit_for_decision(
    *,
    decision: str,
    investigation_id: str,
    candidate_id: str,
    old_edge_id: str,
    new_edge_id: str,
    reviewer: str,
    valid_until: datetime,
    review_notes: str = "",
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Convenience: pick the right emit helper based on the decision
    string. Useful when the review code already validates the decision
    and just needs to fire whichever event is correct.

    Raises ValueError if ``decision`` isn't in REVIEW_DECISIONS."""
    validate_decision(decision)
    if decision == "apply_supersession":
        return emit_supersession_apply(
            investigation_id=investigation_id,
            candidate_id=candidate_id,
            old_edge_id=old_edge_id,
            new_edge_id=new_edge_id,
            new_valid_until=valid_until,
            reviewer=reviewer,
            review_notes=review_notes,
            parent_event_id=parent_event_id,
        )
    if decision == "dismiss_new":
        return emit_supersession_dismiss(
            investigation_id=investigation_id,
            candidate_id=candidate_id,
            edge_id=new_edge_id,
            target="new",
            valid_until=valid_until,
            reviewer=reviewer,
            review_notes=review_notes,
            parent_event_id=parent_event_id,
        )
    if decision == "dismiss_old":
        return emit_supersession_dismiss(
            investigation_id=investigation_id,
            candidate_id=candidate_id,
            edge_id=old_edge_id,
            target="old",
            valid_until=valid_until,
            reviewer=reviewer,
            review_notes=review_notes,
            parent_event_id=parent_event_id,
        )
    # coexist
    return emit_supersession_coexist(
        investigation_id=investigation_id,
        candidate_id=candidate_id,
        reviewer=reviewer,
        review_notes=review_notes,
        parent_event_id=parent_event_id,
    )
