"""GEPA — Genetic-Pareto prompt optimizer (Prime Intellect Phase 2).

Per `integration_prime_intellect.md` item A: 'GEPA on
parameter_extractor only'. GEPA outperforms GRPO by 6% average and
up to 20% across six benchmark tasks while using up to 35x fewer
rollouts. Per ICLR 2026 Oral paper (Agrawal et al., arXiv:2507.19457).

Sprint 11+ of Prime Intellect track. Loop-3-gated for any training-
time application; pre-unlock the optimizer runs offline against
golden-trace fixtures only.

The pattern:
- Maintain a Pareto front of (prompt_variant, score_vector) pairs
- Mutate via prompt-level edits (the autoresearch Wedge 1 mutator
  produces these per `tools/prompt_autoresearch/`)
- Score vector tracks multiple dimensions (rubric_score,
  cost_usd, verifier_pass_rate) so the front captures trade-offs
- Selection is NSGA-II non-dominated sort: keep Pareto-optimal
  variants for the next generation
"""

from .pareto_front import (
    NSGAIIError,
    ParetoFront,
    ScoreVector,
    Variant,
    non_dominated_sort,
)
from .optimizer import (
    GEPAOptimizer,
    GEPAResult,
    optimize_role_prompt,
)

__all__ = [
    "GEPAOptimizer",
    "GEPAResult",
    "NSGAIIError",
    "ParetoFront",
    "ScoreVector",
    "Variant",
    "non_dominated_sort",
    "optimize_role_prompt",
]
