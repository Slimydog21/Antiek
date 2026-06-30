"""Phase 8 skill-patch calibration status.

The SkillPatchGate is intentionally allowed to run in shadow mode while the
operator calibrates epsilon. This module makes that standing state visible: it
summarizes shadow decisions, operator-reviewed decisions, and agreement so the
gate does not stay inert because nobody can see calibration progress.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compounding.skill_growth.gate import PatchDecision, PatchOutcome

REQUIRED_SHADOW_DECISIONS = 10
REQUIRED_AGREEMENT = 0.80


@dataclass(frozen=True)
class Phase8CalibrationRecord:
    """One shadow gate decision plus optional operator review."""

    patch_id: str
    decision: str
    delta: float
    epsilon_required: float
    cohort_size: int
    operator_accepted: bool | None = None
    notes: str = ""

    @property
    def is_shadow(self) -> bool:
        return self.decision == PatchDecision.SHADOW.value

    @property
    def would_accept(self) -> bool:
        return self.delta > self.epsilon_required

    @property
    def reviewed(self) -> bool:
        return self.operator_accepted is not None

    @property
    def agrees_with_operator(self) -> bool | None:
        if self.operator_accepted is None:
            return None
        return self.would_accept == self.operator_accepted


@dataclass(frozen=True)
class Phase8CalibrationStatus:
    """Read-only summary of Phase 8 shadow-mode calibration progress."""

    shadow_decisions_collected: int
    operator_reviewed: int
    agreements: int
    agreement_rate: float | None
    required_shadow_decisions: int = REQUIRED_SHADOW_DECISIONS
    required_agreement: float = REQUIRED_AGREEMENT

    @property
    def calibration_ready(self) -> bool:
        return (
            self.shadow_decisions_collected >= self.required_shadow_decisions
            and self.operator_reviewed >= self.required_shadow_decisions
            and self.agreement_rate is not None
            and self.agreement_rate >= self.required_agreement
        )

    def one_line(self) -> str:
        pct = "n/a" if self.agreement_rate is None else f"{self.agreement_rate:.0%}"
        verdict = "READY" if self.calibration_ready else "NOT_READY"
        return (
            f"{self.shadow_decisions_collected} shadow decisions collected; "
            f"{self.operator_reviewed} operator-reviewed; current epsilon "
            f"agreement = {pct}; {verdict}"
        )


def record_from_patch_outcome(
    outcome: PatchOutcome,
    *,
    operator_accepted: bool | None = None,
) -> Phase8CalibrationRecord:
    """Convert an in-memory gate outcome to the audit record shape."""
    return Phase8CalibrationRecord(
        patch_id=outcome.patch_id,
        decision=outcome.decision.value,
        delta=outcome.delta,
        epsilon_required=outcome.epsilon_required,
        cohort_size=outcome.cohort_size,
        operator_accepted=operator_accepted,
        notes=outcome.notes,
    )


def summarize_calibration(
    records: Iterable[Phase8CalibrationRecord],
    *,
    required_shadow_decisions: int = REQUIRED_SHADOW_DECISIONS,
    required_agreement: float = REQUIRED_AGREEMENT,
) -> Phase8CalibrationStatus:
    """Fold calibration records into the operator-facing status."""
    shadow = [r for r in records if r.is_shadow]
    reviewed = [r for r in shadow if r.reviewed]
    agreements = sum(1 for r in reviewed if r.agrees_with_operator is True)
    agreement_rate = agreements / len(reviewed) if reviewed else None
    return Phase8CalibrationStatus(
        shadow_decisions_collected=len(shadow),
        operator_reviewed=len(reviewed),
        agreements=agreements,
        agreement_rate=agreement_rate,
        required_shadow_decisions=required_shadow_decisions,
        required_agreement=required_agreement,
    )


def _payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Accept either a direct record JSON line or an event-log-shaped row."""
    payload = row.get("payload")
    if isinstance(payload, dict) and "patch_id" in payload:
        return payload
    return row


def _coerce_operator_review(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"accept", "accepted", "true", "yes", "1"}:
            return True
        if lowered in {"reject", "rejected", "false", "no", "0"}:
            return False
    raise ValueError(f"unknown operator review value: {value!r}")


def record_from_mapping(row: dict[str, Any]) -> Phase8CalibrationRecord:
    """Parse a JSON/object record into the calibration record shape."""
    payload = _payload_from_row(row)
    try:
        return Phase8CalibrationRecord(
            patch_id=str(payload["patch_id"]),
            decision=str(payload["decision"]),
            delta=float(payload["delta"]),
            epsilon_required=float(payload["epsilon_required"]),
            cohort_size=int(payload.get("cohort_size", 0)),
            operator_accepted=_coerce_operator_review(
                payload.get("operator_accepted", payload.get("operator_review"))
            ),
            notes=str(payload.get("notes", "")),
        )
    except KeyError as exc:
        raise ValueError(f"phase8 calibration record missing {exc.args[0]!r}") from exc


def load_records_jsonl(path: str | Path) -> list[Phase8CalibrationRecord]:
    """Load calibration records from newline-delimited JSON."""
    records: list[Phase8CalibrationRecord] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{lineno}: expected JSON object")
        records.append(record_from_mapping(row))
    return records


def summarize_jsonl(
    path: str | Path,
    *,
    required_shadow_decisions: int = REQUIRED_SHADOW_DECISIONS,
    required_agreement: float = REQUIRED_AGREEMENT,
) -> Phase8CalibrationStatus:
    """Load JSONL calibration data and return the status summary."""
    return summarize_calibration(
        load_records_jsonl(path),
        required_shadow_decisions=required_shadow_decisions,
        required_agreement=required_agreement,
    )


__all__ = [
    "Phase8CalibrationRecord",
    "Phase8CalibrationStatus",
    "REQUIRED_AGREEMENT",
    "REQUIRED_SHADOW_DECISIONS",
    "load_records_jsonl",
    "record_from_mapping",
    "record_from_patch_outcome",
    "summarize_calibration",
    "summarize_jsonl",
]
