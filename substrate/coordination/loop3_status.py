"""Loop 3 status — read-only coordination summary.

The Loop3 page owns the detailed operator checklist. Coordination needs a
compact G8/OA-004 summary because Loop 3 gates Write/Speak training paths and
multiple engineering deferrals. This module reads the persistent checklist and
the verifier-backed evidence snapshot; it never updates checklist state and
never authorizes training.
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.loop_3.checklist_store import ChecklistSnapshot
from substrate.loop_3.evidence_status import (
    CriterionEvidenceStatus,
    Loop3EvidenceSnapshot,
    snapshot as evidence_snapshot,
)


@dataclass(frozen=True)
class Loop3CriterionStatus:
    criterion: str
    manual_met: bool
    evidence_passed: bool
    evidence_status: str
    evidence_summary: str


@dataclass(frozen=True)
class Loop3CoordinationView:
    criteria: tuple[Loop3CriterionStatus, ...]
    manual_met_count: int
    evidence_passed_count: int
    total_criteria: int
    all_criteria_met: bool
    all_evidence_passed: bool
    env_unlocked: bool
    fully_unlocked: bool
    first_failing_evidence: Loop3CriterionStatus | None
    events_dir: str
    open_weight_policy_file: str


def _criterion_row(
    criterion: str,
    *,
    manual: ChecklistSnapshot,
    evidence: Loop3EvidenceSnapshot,
) -> Loop3CriterionStatus:
    ev: CriterionEvidenceStatus | None = evidence.statuses.get(criterion)
    return Loop3CriterionStatus(
        criterion=criterion,
        manual_met=manual.criteria.get(criterion, False),
        evidence_passed=ev.passed if ev is not None else False,
        evidence_status=ev.status if ev is not None else "MISSING",
        evidence_summary=ev.summary if ev is not None else "evidence missing",
    )


def build_loop3_coordination_view(
    con,
    *,
    evidence: Loop3EvidenceSnapshot | None = None,
) -> Loop3CoordinationView:
    """Read the Loop 3 checklist + evidence snapshot.

    ``con`` is expected to be a read connection. The underlying checklist loader
    only selects rows; evidence verification reads committed artifacts and event
    logs. No call here flips checklist rows or the ``ANTIEK_LOOP3_UNLOCKED`` env
    gate.
    """
    from substrate.loop_3.checklist_store import snapshot as checklist_snapshot

    manual = checklist_snapshot(con)
    evidence = evidence or evidence_snapshot()
    criteria = tuple(
        _criterion_row(criterion, manual=manual, evidence=evidence)
        for criterion in manual.criteria
    )
    first_failing = next((c for c in criteria if not c.evidence_passed), None)
    return Loop3CoordinationView(
        criteria=criteria,
        manual_met_count=sum(1 for c in criteria if c.manual_met),
        evidence_passed_count=sum(1 for c in criteria if c.evidence_passed),
        total_criteria=len(criteria),
        all_criteria_met=manual.all_criteria_met,
        all_evidence_passed=evidence.all_evidence_passed,
        env_unlocked=manual.env_unlocked,
        fully_unlocked=manual.fully_unlocked and evidence.all_evidence_passed,
        first_failing_evidence=first_failing,
        events_dir=evidence.events_dir,
        open_weight_policy_file=evidence.open_weight_policy_file,
    )


__all__ = [
    "Loop3CoordinationView",
    "Loop3CriterionStatus",
    "build_loop3_coordination_view",
]
