"""GEPA optimizer loop."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from .pareto_front import ParetoFront, ScoreVector, Variant


@dataclass(frozen=True)
class GEPAResult:
    """Final result of a GEPA optimization run."""

    pareto_front: list[Variant]
    total_iterations: int
    total_variants_evaluated: int
    rejected_dominated: int


@dataclass
class GEPAOptimizer:
    """Outer loop for genetic-Pareto prompt optimization.

    Per integration_prime_intellect.md item A: scoped to
    parameter_extractor for the first run. Generalizes to other
    roles via the prompt_role parameter."""

    prompt_role: str = "parameter_extractor"
    front: ParetoFront = field(default_factory=ParetoFront)
    iteration_count: int = 0
    variants_evaluated: int = 0
    rejected_dominated: int = 0

    def evaluate_and_admit(
        self,
        *,
        prompt_text: str,
        score: ScoreVector,
        parent_variant_id: str | None = None,
        rationale: str = "",
    ) -> tuple[Variant, bool]:
        """Evaluate one candidate. Returns (variant, was_admitted)."""
        self.variants_evaluated += 1
        variant = Variant(
            variant_id=f"gepa-{self.prompt_role}-{uuid.uuid4().hex[:10]}",
            prompt_text=prompt_text,
            score=score,
            parent_variant_id=parent_variant_id,
            rationale=rationale,
        )
        admitted = self.front.admit(variant)
        if not admitted:
            self.rejected_dominated += 1
        return (variant, admitted)

    def step(
        self,
        *,
        mutator_fn: Callable[[list[Variant]], list[tuple[str, str]]],
        scorer_fn: Callable[[str], ScoreVector],
    ) -> int:
        """One optimizer iteration. The mutator proposes new variants
        from the current Pareto front; each is scored; the front
        updates. Returns the number of admissions this iteration."""
        self.iteration_count += 1
        admitted_this_iter = 0
        proposals = mutator_fn(self.front.variants)
        for prompt_text, rationale in proposals:
            score = scorer_fn(prompt_text)
            _, admitted = self.evaluate_and_admit(
                prompt_text=prompt_text,
                score=score,
                rationale=rationale,
            )
            if admitted:
                admitted_this_iter += 1
        return admitted_this_iter

    def result(self) -> GEPAResult:
        return GEPAResult(
            pareto_front=list(self.front.variants),
            total_iterations=self.iteration_count,
            total_variants_evaluated=self.variants_evaluated,
            rejected_dominated=self.rejected_dominated,
        )


def optimize_role_prompt(
    *,
    role: str,
    seed_prompt: str,
    seed_score: ScoreVector,
    mutator_fn: Callable[[list[Variant]], list[tuple[str, str]]],
    scorer_fn: Callable[[str], ScoreVector],
    max_iterations: int = 10,
) -> GEPAResult:
    """End-to-end GEPA run for one role. Seeds the Pareto front with
    the baseline prompt + score, iterates mutator/scorer up to
    max_iterations, returns the final result."""
    optimizer = GEPAOptimizer(prompt_role=role)
    optimizer.evaluate_and_admit(
        prompt_text=seed_prompt,
        score=seed_score,
        rationale="baseline seed",
    )
    for _ in range(max_iterations):
        optimizer.step(mutator_fn=mutator_fn, scorer_fn=scorer_fn)
    return optimizer.result()
