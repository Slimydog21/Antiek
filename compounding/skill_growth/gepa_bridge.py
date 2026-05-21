"""Bridge a GEPA optimization run → Phase 8 skill-patch gate.

Per master-spec §13.6 + integration_autoresearch.md Wedge 2: GEPA
produces a Pareto front of prompt variants for a role; the Phase 8
gate decides which (if any) variants land as the new role prompt.
This bridge is the single, testable handoff.

Flow:
  1. GEPA optimizer returns a ``GEPAResult`` with a Pareto front.
  2. The bridge sorts the front by a caller-supplied composite
     preference (default: simple lexicographic on the score vector).
  3. Each variant is proposed in order to the Phase 8 gate, scored
     against the baseline.
  4. In enforcing mode, the bridge stops at the first ACCEPT (the
     accepted variant becomes the new role prompt). In shadow mode,
     every variant runs through the gate so the calibration data is
     collected uniformly.

The bridge does NOT apply patches itself; it returns the
``BridgeOutcome`` sequence and lets the caller wire ``apply_fn`` per
variant. This matches the existing ``apply_patch_with_gate`` contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from tools.gepa.pareto_front import ScoreVector, Variant
from tools.gepa.optimizer import GEPAResult

from .gate import (
    PatchDecision,
    PatchOutcome,
    SkillPatchGate,
)


CompositeKeyFn = Callable[[ScoreVector], float]
"""Optional caller-supplied scoring key for ordering Pareto-front
variants. Default sums the objective vector — adequate when all
dimensions are normalized + 'higher is better' (the canonical GEPA
ScoreVector contract)."""


def _default_composite(score: ScoreVector) -> float:
    """Default ordering: sum of the four named ScoreVector fields
    (rubric_score + verifier_pass_rate + cost_penalty +
    grounding_preserved). Per the master ScoreVector contract all four
    follow 'higher is better' so the sum is a valid total-order tie-
    breaker for variants already on the Pareto front (which by
    definition are non-dominated, so no single field strictly orders
    them). Production callers override with a domain-specific
    weighting via ``composite_key``.
    """
    return float(
        score.rubric_score
        + score.verifier_pass_rate
        + score.cost_penalty
        + score.grounding_preserved
    )


@dataclass(frozen=True)
class BridgeOutcome:
    """One Phase-8-gate decision arising from a GEPA Pareto variant."""

    variant_id: str
    variant_prompt: str
    variant_rationale: str
    patch_outcome: PatchOutcome


@dataclass
class GepaToPhase8Bridge:
    """Hands GEPA Pareto-front variants to the Phase 8 gate in
    composite-preference order. Emits one ``BridgeOutcome`` per
    variant inspected.

    In enforcing mode, iteration stops at the first ACCEPT (subsequent
    variants are NOT proposed — the accepted one is the new role
    prompt). In shadow mode, every variant runs the gate so the
    calibration period collects uniform data per §6.4.
    """

    gate: SkillPatchGate
    composite_key: CompositeKeyFn = field(default=_default_composite)

    def bridge(
        self,
        *,
        result: GEPAResult,
        baseline_score: float,
        cohort_size: int,
        backtest_fn: Callable[[Variant], float],
        baseline_variant_id: Optional[str] = None,
    ) -> list[BridgeOutcome]:
        """Walk the Pareto front variants in preference order and
        run each through the Phase 8 gate.

        Args:
          result: the completed GEPAResult
          baseline_score: the current production baseline score
          cohort_size: number of backtest cases used for evaluation
          backtest_fn: maps a variant → its backtest score (≥0; the
            scale matches baseline_score's scale)
          baseline_variant_id: optional variant_id of the current
            production prompt; this variant is SKIPPED so we don't
            grade the baseline against itself.
        """
        candidates: list[Variant] = []
        for variant in result.pareto_front:
            if (
                baseline_variant_id is not None
                and variant.variant_id == baseline_variant_id
            ):
                continue
            candidates.append(variant)

        # Sort by composite preference (descending — highest preferred first).
        candidates.sort(
            key=lambda v: self.composite_key(v.score),
            reverse=True,
        )

        outcomes: list[BridgeOutcome] = []
        for variant in candidates:
            candidate_score = backtest_fn(variant)
            patch_outcome = self.gate.decide(
                baseline_backtest_score=baseline_score,
                candidate_backtest_score=candidate_score,
                cohort_size=cohort_size,
            )
            outcomes.append(BridgeOutcome(
                variant_id=variant.variant_id,
                variant_prompt=variant.prompt_text,
                variant_rationale=variant.rationale,
                patch_outcome=patch_outcome,
            ))
            # In enforcing mode, stop at the first accepted variant —
            # that one becomes the new role prompt. Shadow mode runs
            # every variant for uniform calibration data.
            if (
                self.gate.mode == "enforcing"
                and patch_outcome.decision == PatchDecision.ACCEPT
            ):
                break

        return outcomes


def bridge_gepa_result_to_phase8(
    *,
    gate: SkillPatchGate,
    result: GEPAResult,
    baseline_score: float,
    cohort_size: int,
    backtest_fn: Callable[[Variant], float],
    baseline_variant_id: Optional[str] = None,
    composite_key: Optional[CompositeKeyFn] = None,
) -> list[BridgeOutcome]:
    """One-shot convenience wrapper. Builds the bridge with the
    supplied gate + composite key and runs ``bridge()``."""
    b = GepaToPhase8Bridge(
        gate=gate,
        composite_key=composite_key or _default_composite,
    )
    return b.bridge(
        result=result,
        baseline_score=baseline_score,
        cohort_size=cohort_size,
        backtest_fn=backtest_fn,
        baseline_variant_id=baseline_variant_id,
    )


__all__ = [
    "BridgeOutcome",
    "CompositeKeyFn",
    "GepaToPhase8Bridge",
    "bridge_gepa_result_to_phase8",
]
