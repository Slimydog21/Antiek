"""GEPA optimizer tests (Prime Intellect Phase 2, integration spec item A)."""

from __future__ import annotations

from tools.gepa import (
    GEPAOptimizer,
    ParetoFront,
    ScoreVector,
    Variant,
    non_dominated_sort,
    optimize_role_prompt,
)

# ── Score-vector dominance ──────────────────────────────────────────


def test_dominates_strict_better_all_dimensions():
    a = ScoreVector(0.8, 0.9, -0.10, 0.85)
    b = ScoreVector(0.7, 0.8, -0.20, 0.80)
    assert a.dominates(b)
    assert not b.dominates(a)


def test_dominates_requires_strict_gt_in_at_least_one():
    """Equal in all → no dominance either direction."""
    a = ScoreVector(0.8, 0.9, -0.10, 0.85)
    b = ScoreVector(0.8, 0.9, -0.10, 0.85)
    assert not a.dominates(b)
    assert not b.dominates(a)


def test_dominance_fails_if_worse_in_any_dimension():
    """If a > b in some but worse in any other → no dominance."""
    a = ScoreVector(0.9, 0.8, -0.30, 0.85)  # better rubric, worse cost
    b = ScoreVector(0.8, 0.8, -0.10, 0.85)
    assert not a.dominates(b)
    assert not b.dominates(a)


# ── Non-dominated sort ──────────────────────────────────────────────


def test_non_dominated_sort_returns_pareto_fronts():
    """Pareto-front partition: front[0] dominates all subsequent."""
    variants = [
        Variant("v1", "p1", ScoreVector(0.9, 0.9, -0.1, 0.9)),  # Pareto
        Variant("v2", "p2", ScoreVector(0.8, 0.9, -0.05, 0.9)),  # Pareto (cheaper)
        Variant("v3", "p3", ScoreVector(0.7, 0.7, -0.3, 0.7)),   # dominated by v1
    ]
    fronts = non_dominated_sort(variants)
    front_0_ids = {v.variant_id for v in fronts[0]}
    assert "v1" in front_0_ids
    assert "v2" in front_0_ids  # not dominated (cheaper than v1)
    assert "v3" not in front_0_ids


def test_non_dominated_sort_empty():
    assert non_dominated_sort([]) == []


# ── Pareto front ────────────────────────────────────────────────────


def test_admit_first_variant():
    front = ParetoFront()
    v = Variant("v1", "prompt 1", ScoreVector(0.8, 0.8, -0.1, 0.8))
    assert front.admit(v) is True
    assert len(front.variants) == 1


def test_admit_rejects_dominated_candidate():
    front = ParetoFront()
    strong = Variant("v1", "p1", ScoreVector(0.9, 0.9, -0.05, 0.9))
    weak = Variant("v2", "p2", ScoreVector(0.5, 0.5, -0.5, 0.5))
    front.admit(strong)
    assert front.admit(weak) is False
    assert weak not in front.variants


def test_admit_evicts_dominated_existing():
    """A candidate that dominates existing front members evicts them."""
    front = ParetoFront()
    weak = Variant("v1", "p1", ScoreVector(0.5, 0.5, -0.5, 0.5))
    front.admit(weak)

    dominating = Variant("v2", "p2", ScoreVector(0.9, 0.9, -0.05, 0.9))
    front.admit(dominating)

    assert weak not in front.variants
    assert dominating in front.variants


# ── Optimizer ───────────────────────────────────────────────────────


def test_optimizer_seed_and_step():
    optimizer = GEPAOptimizer(prompt_role="parameter_extractor")
    v, admitted = optimizer.evaluate_and_admit(
        prompt_text="seed prompt",
        score=ScoreVector(0.7, 0.7, -0.10, 0.7),
        rationale="baseline",
    )
    assert admitted is True
    assert optimizer.variants_evaluated == 1

    def mutator(current):
        # Propose one slightly improved variant.
        return [("seed prompt + tweak", "drop hedging modifiers")]

    def scorer(prompt):
        # Better rubric, same cost.
        return ScoreVector(0.85, 0.7, -0.10, 0.7)

    admitted_count = optimizer.step(mutator_fn=mutator, scorer_fn=scorer)
    assert admitted_count == 1


def test_optimize_role_prompt_end_to_end():
    def mutator(current):
        # Produce one variant per step.
        n = len(current)
        return [(f"variant-{n}", f"iteration-{n}")]

    def scorer(prompt):
        # Each variant slightly better than the last.
        # Parse the variant number from prompt for determinism.
        try:
            n = int(prompt.split("-")[-1])
        except (IndexError, ValueError):
            n = 0
        return ScoreVector(
            rubric_score=min(0.99, 0.6 + n * 0.05),
            verifier_pass_rate=min(0.99, 0.6 + n * 0.05),
            cost_penalty=-0.10,
            grounding_preserved=0.9,
        )

    result = optimize_role_prompt(
        role="parameter_extractor",
        seed_prompt="initial",
        seed_score=ScoreVector(0.6, 0.6, -0.10, 0.9),
        mutator_fn=mutator,
        scorer_fn=scorer,
        max_iterations=5,
    )
    assert result.total_iterations == 5
    assert result.total_variants_evaluated >= 5
    # The final Pareto front should include the best variants.
    assert len(result.pareto_front) >= 1
