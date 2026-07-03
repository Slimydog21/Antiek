"""Supersession middleware — contradiction review queue.

Architecture_notes §4: contradictions become TASKS, not actions. This
module never auto-applies supersession — it captures candidates and
fires audit events when a human reviewer decides. The DB-touching
detector and ``apply_review`` path are being built in SPR-02 of the
Contradiction & Supersession spec; emit helpers + pure validators
ship now.
"""

from .supersession import (
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

__all__ = [
    "REVIEW_DECISIONS",
    "CONTRADICTION_TYPES",
    "SupersessionVerdict",
    "DEFAULT_UNCLASSIFIED_VERDICT",
    "validate_decision",
    "new_candidate_id",
    "emit_supersession_apply",
    "emit_supersession_dismiss",
    "emit_supersession_coexist",
    "emit_for_decision",
]
