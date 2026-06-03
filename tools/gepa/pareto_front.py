"""Pareto-front mechanics for GEPA."""

from __future__ import annotations

from dataclasses import dataclass, field


class NSGAIIError(Exception):
    pass


@dataclass(frozen=True)
class ScoreVector:
    """Multi-dimensional score for a prompt variant.

    All dimensions follow the convention 'higher is better'. Cost
    is captured as a negative (cost penalty)."""

    rubric_score: float           # [0, 1]; higher better
    verifier_pass_rate: float     # [0, 1]; higher better
    cost_penalty: float           # negative USD; higher (less negative) better
    grounding_preserved: float    # [0, 1]; higher better

    def dominates(self, other: ScoreVector) -> bool:
        """Pareto-dominance: self ≥ other in all dimensions AND > in
        at least one."""
        ge_all = (
            self.rubric_score >= other.rubric_score
            and self.verifier_pass_rate >= other.verifier_pass_rate
            and self.cost_penalty >= other.cost_penalty
            and self.grounding_preserved >= other.grounding_preserved
        )
        if not ge_all:
            return False
        gt_any = (
            self.rubric_score > other.rubric_score
            or self.verifier_pass_rate > other.verifier_pass_rate
            or self.cost_penalty > other.cost_penalty
            or self.grounding_preserved > other.grounding_preserved
        )
        return gt_any


@dataclass(frozen=True)
class Variant:
    """One prompt variant + its score vector."""

    variant_id: str
    prompt_text: str
    score: ScoreVector
    parent_variant_id: str | None = None
    rationale: str = ""


def non_dominated_sort(variants: list[Variant]) -> list[list[Variant]]:
    """NSGA-II-style non-dominated sort. Returns a list of fronts;
    fronts[0] is the Pareto-optimal set; fronts[1] is dominated by
    fronts[0] only; etc.

    Standard NSGA-II algorithm. The substrate uses this to select
    the next generation: keep all of front[0], then fill remaining
    slots from front[1], etc.
    """
    if not variants:
        return []

    domination_count = {v.variant_id: 0 for v in variants}
    dominated = {v.variant_id: [] for v in variants}

    for i, v1 in enumerate(variants):
        for j, v2 in enumerate(variants):
            if i == j:
                continue
            if v1.score.dominates(v2.score):
                dominated[v1.variant_id].append(v2.variant_id)
            elif v2.score.dominates(v1.score):
                domination_count[v1.variant_id] += 1

    fronts: list[list[Variant]] = []
    by_id = {v.variant_id: v for v in variants}

    current_front_ids = [vid for vid, c in domination_count.items() if c == 0]
    while current_front_ids:
        fronts.append([by_id[vid] for vid in current_front_ids])
        next_front_ids: list[str] = []
        for vid in current_front_ids:
            for dominated_id in dominated[vid]:
                domination_count[dominated_id] -= 1
                if domination_count[dominated_id] == 0:
                    next_front_ids.append(dominated_id)
        current_front_ids = next_front_ids

    return fronts


@dataclass
class ParetoFront:
    """A maintained Pareto front of variants. Adding a dominated
    variant is a no-op; adding a dominating variant evicts the
    dominated ones."""

    variants: list[Variant] = field(default_factory=list)

    def admit(self, candidate: Variant) -> bool:
        """Try to admit candidate to the front. Returns True if
        admitted (and possibly evicted), False if dominated by
        existing front members."""
        # Reject if any existing variant dominates the candidate.
        for existing in self.variants:
            if existing.score.dominates(candidate.score):
                return False
        # Evict any existing variants the candidate dominates.
        self.variants = [
            v for v in self.variants
            if not candidate.score.dominates(v.score)
        ]
        self.variants.append(candidate)
        return True
