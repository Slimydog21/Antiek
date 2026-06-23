"""Phase 8 skill-patch accept/reject gate (autoresearch Wedge 2)."""

from __future__ import annotations

import enum
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime


class PatchDecision(str, enum.Enum):
    """Decision outcomes for a candidate skill patch."""

    ACCEPT = "accept"
    REJECT = "reject"
    SHADOW = "shadow"  # gate ran in shadow mode; outcome recorded but patch applied


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PatchOutcome:
    patch_id: str
    decision: PatchDecision
    baseline_backtest_score: float
    candidate_backtest_score: float
    delta: float
    epsilon_required: float
    cohort_size: int
    notes: str = ""
    decided_at: str = field(default_factory=_now_iso)


@dataclass
class SkillPatchGate:
    """Per integration_autoresearch.md Wedge 2: shadow mode runs the
    gate but applies the patch anyway; enforcing mode applies only on
    accept. Operator switches via the `mode` field.

    Acceptance criterion: candidate_backtest_score > baseline +
    epsilon, where epsilon must exceed 2σ of no-op-patch variance
    (calibrated separately; the shadow-mode period collects the data
    that calibrates epsilon).

    Required calibration BEFORE flipping to enforcing per
    integration_autoresearch.md §6.4: 'run the gate in shadow-mode
    for 10+ investigations — compute the accept/reject decision but
    apply the patch regardless. Compare shadow decisions to operator's
    manual review. Tune ε until shadow ≥80% agrees with operator.
    THEN flip the gate to enforcing.'
    """

    mode: str = "shadow"  # "shadow" | "enforcing"
    epsilon: float = 0.02
    minimum_cohort_size: int = 50  # per §6.3 architectural threshold

    def decide(
        self,
        *,
        baseline_backtest_score: float,
        candidate_backtest_score: float,
        cohort_size: int,
    ) -> PatchOutcome:
        """Run the gate. Returns a PatchOutcome including the
        decision + score breakdown. The CALLER decides whether to
        actually apply the patch based on the decision + mode (see
        apply_patch_with_gate for the canonical flow)."""
        patch_id = f"patch-{uuid.uuid4().hex[:12]}"
        delta = candidate_backtest_score - baseline_backtest_score

        if self.mode == "shadow":
            decision = PatchDecision.SHADOW
            note = (
                f"shadow-mode: delta={delta:.4f}, "
                f"would-be-accept={delta > self.epsilon}; "
                f"patch applied regardless"
            )
        else:
            if cohort_size < self.minimum_cohort_size:
                decision = PatchDecision.REJECT
                note = (
                    f"cohort_size={cohort_size} < minimum "
                    f"{self.minimum_cohort_size}; backtest score not "
                    f"discriminating at this scale"
                )
            elif delta > self.epsilon:
                decision = PatchDecision.ACCEPT
                note = f"delta={delta:.4f} exceeds epsilon={self.epsilon}"
            else:
                decision = PatchDecision.REJECT
                note = (
                    f"delta={delta:.4f} ≤ epsilon={self.epsilon}; "
                    f"patch indistinguishable from no-op"
                )

        return PatchOutcome(
            patch_id=patch_id,
            decision=decision,
            baseline_backtest_score=baseline_backtest_score,
            candidate_backtest_score=candidate_backtest_score,
            delta=delta,
            epsilon_required=self.epsilon,
            cohort_size=cohort_size,
            notes=note,
        )


def propose_skill_patch(
    *,
    domain: str,
    proposed_skill_text: str,
    investigation_id: str,
) -> dict:
    """Wrap a candidate skill-patch in a proposal envelope. Real
    patch application is operator-driven (or Sprint 20-21
    Phase-8-with-gate driven); this function only formats the
    proposal."""
    return {
        "patch_id": f"patch-{uuid.uuid4().hex[:12]}",
        "domain": domain,
        "proposed_text": proposed_skill_text,
        "source_investigation_id": investigation_id,
        "proposed_at": _now_iso(),
    }


def apply_patch_with_gate(
    *,
    gate: SkillPatchGate,
    baseline_backtest_score: float,
    candidate_backtest_score: float,
    cohort_size: int,
    apply_fn: Callable[[], None],
) -> PatchOutcome:
    """Canonical Phase-8-with-gate flow. Runs the gate; in shadow
    mode applies the patch regardless; in enforcing mode applies
    only on ACCEPT."""
    outcome = gate.decide(
        baseline_backtest_score=baseline_backtest_score,
        candidate_backtest_score=candidate_backtest_score,
        cohort_size=cohort_size,
    )
    if outcome.decision == PatchDecision.SHADOW or outcome.decision == PatchDecision.ACCEPT:
        apply_fn()
    # On REJECT, patch is NOT applied; caller logs the rejection.
    return outcome
