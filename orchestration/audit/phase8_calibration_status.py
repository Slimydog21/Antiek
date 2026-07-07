"""Phase-8 gate calibration status.

This module reports whether shadow gate decisions have accumulated enough
operator-reviewed evidence to justify flipping Phase 8 into enforcing mode.
It is observe-only: it reads typed gate-decision events and never mutates
skills, phase logs, or trajectory rows.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from substrate.event_log import trajectory
from substrate.schemas import ActionType, Event, SkillPatchGateDecidedPayload

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


def _payload_from_row(row: Mapping[str, Any]) -> SkillPatchGateDecidedPayload | None:
    if row.get("action_type") != ActionType.SKILL_PATCH_GATE_DECIDED.value:
        return None
    event = Event.model_validate(row)
    payload = event.payload
    if isinstance(payload, SkillPatchGateDecidedPayload):
        return payload
    return None


def summarize_phase8_calibration(
    payloads: Iterable[SkillPatchGateDecidedPayload],
    *,
    required_shadow_decisions: int = DEFAULT_REQUIRED_SHADOW_DECISIONS,
    required_operator_agreement: float = DEFAULT_REQUIRED_OPERATOR_AGREEMENT,
) -> Phase8CalibrationStatus:
    """Summarize shadow-mode gate decisions into enforcing-readiness status."""
    shadow_payloads = [payload for payload in payloads if payload.mode == "shadow"]
    reviewed = [payload for payload in shadow_payloads if payload.operator_reviewed]
    agreed = [payload for payload in reviewed if payload.operator_agreed is True]
    agreement_rate = None if not reviewed else len(agreed) / len(reviewed)
    ready = (
        len(shadow_payloads) >= required_shadow_decisions
        and len(reviewed) >= required_shadow_decisions
        and agreement_rate is not None
        and agreement_rate >= required_operator_agreement
    )
    return Phase8CalibrationStatus(
        shadow_decisions_collected=len(shadow_payloads),
        operator_reviewed=len(reviewed),
        operator_agreed=len(agreed),
        agreement_rate=agreement_rate,
        required_shadow_decisions=required_shadow_decisions,
        required_operator_agreement=required_operator_agreement,
        ready_for_enforcing=ready,
    )


def phase8_calibration_status(
    investigation_ids: Sequence[str],
    *,
    events_dir: str | None = None,
    required_shadow_decisions: int = DEFAULT_REQUIRED_SHADOW_DECISIONS,
    required_operator_agreement: float = DEFAULT_REQUIRED_OPERATOR_AGREEMENT,
) -> Phase8CalibrationStatus:
    """Load gate-decision events for the given investigations and summarize them."""
    payloads: list[SkillPatchGateDecidedPayload] = []
    for investigation_id in investigation_ids:
        for row in trajectory(investigation_id, events_dir=events_dir):
            payload = _payload_from_row(row)
            if payload is not None:
                payloads.append(payload)
    return summarize_phase8_calibration(
        payloads,
        required_shadow_decisions=required_shadow_decisions,
        required_operator_agreement=required_operator_agreement,
    )
