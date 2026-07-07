"""Phase-8 gate calibration status.

This module reports whether shadow gate decisions have accumulated enough
operator-reviewed evidence to justify flipping Phase 8 into enforcing mode.
It never mutates skills or phase logs. Operator review is captured as a second
append-only typed event linked to the original gate-decision event.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from substrate.event_log import emit_typed, trajectory
from substrate.schemas import (
    ActionType,
    Event,
    SkillPatchGateDecidedPayload,
    SkillPatchGateReviewedPayload,
)

DEFAULT_REQUIRED_SHADOW_DECISIONS = 10
DEFAULT_REQUIRED_OPERATOR_AGREEMENT = 0.80


@dataclass(frozen=True)
class Phase8CalibrationStatus:
    """Aggregate readiness status for the Phase-8 skill-patch gate."""

    shadow_decisions_collected: int
    operator_reviewed: int
    operator_agreed: int
    agreement_rate: float | None
    required_shadow_decisions: int = DEFAULT_REQUIRED_SHADOW_DECISIONS
    required_operator_agreement: float = DEFAULT_REQUIRED_OPERATOR_AGREEMENT
    ready_for_enforcing: bool = False

    @property
    def summary(self) -> str:
        agreement = (
            "n/a" if self.agreement_rate is None
            else f"{self.agreement_rate * 100:.0f}%"
        )
        return (
            f"{self.shadow_decisions_collected} shadow decisions collected; "
            f"{self.operator_reviewed} operator-reviewed; "
            f"current epsilon agreement = {agreement}"
        )


@dataclass(frozen=True)
class _DecisionRecord:
    event_id: str
    payload: SkillPatchGateDecidedPayload


def _decision_from_row(row: Mapping[str, Any]) -> _DecisionRecord | None:
    if row.get("action_type") != ActionType.SKILL_PATCH_GATE_DECIDED.value:
        return None
    event = Event.model_validate(row)
    payload = event.payload
    if isinstance(payload, SkillPatchGateDecidedPayload):
        return _DecisionRecord(event_id=event.event_id, payload=payload)
    return None


def _review_from_row(row: Mapping[str, Any]) -> SkillPatchGateReviewedPayload | None:
    if row.get("action_type") != ActionType.SKILL_PATCH_GATE_REVIEWED.value:
        return None
    event = Event.model_validate(row)
    payload = event.payload
    if isinstance(payload, SkillPatchGateReviewedPayload):
        return payload
    return None


def _review_for_decision(
    decision: _DecisionRecord,
    reviews: Iterable[SkillPatchGateReviewedPayload],
) -> SkillPatchGateReviewedPayload | None:
    matched: SkillPatchGateReviewedPayload | None = None
    for review in reviews:
        if (
            review.decision_event_id == decision.event_id
            or matched is None and review.patch_id == decision.payload.patch_id
        ):
            matched = review
    return matched


def record_phase8_gate_review(
    *,
    investigation_id: str,
    synthesis_id: str,
    patch_id: str,
    decision_event_id: str,
    reviewer: str,
    operator_accept: bool,
    review_notes: str = "",
    events_dir: str | None = None,
) -> str | None:
    """Append an operator review event for one Phase-8 gate decision."""
    return emit_typed(
        investigation_id,
        SkillPatchGateReviewedPayload(
            synthesis_id=synthesis_id,
            patch_id=patch_id,
            decision_event_id=decision_event_id,
            reviewer=reviewer,
            operator_accept=operator_accept,
            review_notes=review_notes,
        ),
        synthesis_id=synthesis_id,
        role="phase8_gate_review",
        events_dir=events_dir,
    )


def _summarize_records(
    decisions: Iterable[_DecisionRecord],
    *,
    reviews: Iterable[SkillPatchGateReviewedPayload] = (),
    required_shadow_decisions: int = DEFAULT_REQUIRED_SHADOW_DECISIONS,
    required_operator_agreement: float = DEFAULT_REQUIRED_OPERATOR_AGREEMENT,
) -> Phase8CalibrationStatus:
    shadow_decisions = [
        decision for decision in decisions if decision.payload.mode == "shadow"
    ]
    review_list = list(reviews)
    reviewed: list[bool] = []
    for decision in shadow_decisions:
        review = _review_for_decision(decision, review_list)
        if review is not None:
            reviewed.append(review.operator_accept == decision.payload.would_accept)
        elif decision.payload.operator_reviewed:
            reviewed.append(decision.payload.operator_agreed is True)
    agreed = [agreement for agreement in reviewed if agreement]
    agreement_rate = None if not reviewed else len(agreed) / len(reviewed)
    ready = (
        len(shadow_decisions) >= required_shadow_decisions
        and len(reviewed) >= required_shadow_decisions
        and agreement_rate is not None
        and agreement_rate >= required_operator_agreement
    )
    return Phase8CalibrationStatus(
        shadow_decisions_collected=len(shadow_decisions),
        operator_reviewed=len(reviewed),
        operator_agreed=len(agreed),
        agreement_rate=agreement_rate,
        required_shadow_decisions=required_shadow_decisions,
        required_operator_agreement=required_operator_agreement,
        ready_for_enforcing=ready,
    )


def summarize_phase8_calibration(
    payloads: Iterable[SkillPatchGateDecidedPayload],
    *,
    reviews: Iterable[SkillPatchGateReviewedPayload] = (),
    required_shadow_decisions: int = DEFAULT_REQUIRED_SHADOW_DECISIONS,
    required_operator_agreement: float = DEFAULT_REQUIRED_OPERATOR_AGREEMENT,
) -> Phase8CalibrationStatus:
    """Summarize shadow-mode gate decisions into enforcing-readiness status."""
    return _summarize_records(
        [_DecisionRecord(event_id="", payload=payload) for payload in payloads],
        reviews=reviews,
        required_shadow_decisions=required_shadow_decisions,
        required_operator_agreement=required_operator_agreement,
    )


def phase8_calibration_status(
    investigation_ids: Sequence[str],
    *,
    events_dir: str | None = None,
    required_shadow_decisions: int = DEFAULT_REQUIRED_SHADOW_DECISIONS,
    required_operator_agreement: float = DEFAULT_REQUIRED_OPERATOR_AGREEMENT,
) -> Phase8CalibrationStatus:
    """Load gate-decision events for the given investigations and summarize them."""
    decisions: list[_DecisionRecord] = []
    reviews: list[SkillPatchGateReviewedPayload] = []
    for investigation_id in investigation_ids:
        for row in trajectory(investigation_id, events_dir=events_dir):
            decision = _decision_from_row(row)
            if decision is not None:
                decisions.append(decision)
                continue
            review = _review_from_row(row)
            if review is not None:
                reviews.append(review)

    return _summarize_records(
        decisions,
        reviews=reviews,
        required_shadow_decisions=required_shadow_decisions,
        required_operator_agreement=required_operator_agreement,
    )
