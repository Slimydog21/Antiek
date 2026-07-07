"""Phase 8 skill-patch accept/reject gate (autoresearch Wedge 2)."""

from __future__ import annotations

import enum
import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime


class PatchDecision(enum.StrEnum):
    """Decision outcomes for a candidate skill patch."""

    ACCEPT = "accept"
    REJECT = "reject"
    SHADOW = "shadow"  # gate ran in shadow mode; outcome recorded but patch applied


PHASE8_MODE_ENV = "ANTIEK_PHASE8_MODE"
PHASE8_EPSILON_ENV = "ANTIEK_PHASE8_EPSILON"
PHASE8_MINIMUM_COHORT_SIZE_ENV = "ANTIEK_PHASE8_MINIMUM_COHORT_SIZE"

PHASE8_MODE_SHADOW = "shadow"
PHASE8_MODE_ENFORCING = "enforcing"
VALID_PHASE8_MODES = frozenset({PHASE8_MODE_SHADOW, PHASE8_MODE_ENFORCING})
DEFAULT_PHASE8_EPSILON = 0.02
DEFAULT_PHASE8_MINIMUM_COHORT_SIZE = 50


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

    mode: str = PHASE8_MODE_SHADOW
    epsilon: float = DEFAULT_PHASE8_EPSILON
    minimum_cohort_size: int = DEFAULT_PHASE8_MINIMUM_COHORT_SIZE
    calibration_ready: bool = True
    calibration_notes: str = ""

    def __post_init__(self) -> None:
        if self.mode not in VALID_PHASE8_MODES:
            raise ValueError(
                f"Phase 8 gate mode must be one of "
                f"{sorted(VALID_PHASE8_MODES)!r}; got {self.mode!r}"
            )
        if self.epsilon < 0:
            raise ValueError("Phase 8 gate epsilon must be >= 0")
        if self.minimum_cohort_size < 1:
            raise ValueError("Phase 8 gate minimum_cohort_size must be >= 1")

    def decide(
        self,
        *,
        baseline_backtest_score: float,
        candidate_backtest_score: float,
        cohort_size: int,
        candidate_evidence_ready: bool = True,
        candidate_evidence_notes: str = "",
    ) -> PatchOutcome:
        """Run the gate. Returns a PatchOutcome including the
        decision + score breakdown. The CALLER decides whether to
        actually apply the patch based on the decision + mode (see
        apply_patch_with_gate for the canonical flow)."""
        patch_id = f"patch-{uuid.uuid4().hex[:12]}"
        delta = candidate_backtest_score - baseline_backtest_score

        if self.mode == PHASE8_MODE_SHADOW:
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
            elif not self.calibration_ready:
                decision = PatchDecision.REJECT
                note = "phase8 calibration evidence not ready for enforcing"
                if self.calibration_notes:
                    note = f"{note}: {self.calibration_notes}"
            elif not candidate_evidence_ready:
                decision = PatchDecision.REJECT
                note = "phase8 candidate replay evidence not ready"
                if candidate_evidence_notes:
                    note = f"{note}: {candidate_evidence_notes}"
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
) -> dict[str, str]:
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
    candidate_evidence_ready: bool = True,
    candidate_evidence_notes: str = "",
) -> PatchOutcome:
    """Canonical Phase-8-with-gate flow. Runs the gate; in shadow
    mode applies the patch regardless; in enforcing mode applies
    only on ACCEPT."""
    outcome = gate.decide(
        baseline_backtest_score=baseline_backtest_score,
        candidate_backtest_score=candidate_backtest_score,
        cohort_size=cohort_size,
        candidate_evidence_ready=candidate_evidence_ready,
        candidate_evidence_notes=candidate_evidence_notes,
    )
    if outcome.decision == PatchDecision.SHADOW or outcome.decision == PatchDecision.ACCEPT:
        apply_fn()
    # On REJECT, patch is NOT applied; caller logs the rejection.
    return outcome


def _parse_float_env(
    env: Mapping[str, str],
    name: str,
    default: float,
) -> float:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float; got {raw!r}") from exc


def _parse_int_env(
    env: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer; got {raw!r}") from exc


def phase8_gate_from_env(
    env: Mapping[str, str] | None = None,
    *,
    calibration_ready: bool = True,
    calibration_notes: str = "",
) -> SkillPatchGate:
    """Build the Phase-8 gate from runtime config.

    The default remains shadow mode. Invalid config raises rather than
    silently degrading to shadow, because an operator-requested
    enforcing posture must either be real or fail visibly. Callers that
    have loaded shadow/operator-review evidence pass its readiness here;
    the gate refuses enforcing accepts when that evidence is not ready.
    """
    source = os.environ if env is None else env
    mode = source.get(PHASE8_MODE_ENV, PHASE8_MODE_SHADOW).strip().lower()
    return SkillPatchGate(
        mode=mode or PHASE8_MODE_SHADOW,
        epsilon=_parse_float_env(
            source, PHASE8_EPSILON_ENV, DEFAULT_PHASE8_EPSILON
        ),
        minimum_cohort_size=_parse_int_env(
            source,
            PHASE8_MINIMUM_COHORT_SIZE_ENV,
            DEFAULT_PHASE8_MINIMUM_COHORT_SIZE,
        ),
        calibration_ready=calibration_ready,
        calibration_notes=calibration_notes,
    )
