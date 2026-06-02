"""Prompt-autoresearch outer loop.

Per integration_autoresearch.md §5: propose → execute → measure →
gate. The runner reads the role's program.md + current prompt.py,
the operator's hypothesis (or a mutator's proposal), replays golden
traces, scores the composite, accepts or rejects.

LOCAL-ONLY enforcement: refuses to run if ANTIEK_ENV=production.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from .budget import BudgetCap, BudgetExceeded
from .score import CompositeScore, composite_score


class ProductionEnvironmentRefusal(Exception):
    """Raised if the runner detects production env markers.

    Per master-spec §14.2: prompt autoresearch is local-only and
    NEVER touches the production VM until ratified."""


def _check_local_only() -> None:
    env = os.environ.get("ANTIEK_ENV", "").lower()
    if env == "production":
        raise ProductionEnvironmentRefusal(
            "prompt_autoresearch is local-only per master-spec §14.2; "
            "set ANTIEK_ENV != 'production' before running."
        )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class PromptMutation:
    """A proposed change to a role's prompt. The mutator (which can
    be a coding agent or operator) produces these; the runner
    executes them against golden traces."""

    mutation_id: str
    role: str
    parent_baseline_id: str | None
    proposed_prompt: str  # the candidate new prompt text
    rationale: str  # one-line description of the change
    proposed_at: str = field(default_factory=_now_iso)


@dataclass
class PromptMutationOutcome:
    """Result of executing one mutation against golden traces."""

    mutation_id: str
    accepted: bool
    baseline_score: float
    candidate_score: float
    delta: float
    epsilon_required: float
    composite_breakdown: CompositeScore
    cost_usd: Decimal
    notes: str = ""


@dataclass
class PromptAutoresearchRunner:
    """The outer loop. Operator constructs with a role name + golden
    traces + a scoring backend; calls run_iteration() per candidate
    mutation.

    Acceptance rule per integration_autoresearch.md §5.3:
      candidate.total > baseline.total + epsilon
    where epsilon must exceed 2σ of no-op-mutator variance (the
    calibration step is run separately; the calibrated value is
    injected here).
    """

    role: str
    budget: BudgetCap = field(default_factory=BudgetCap)
    epsilon: float = 0.05  # placeholder; calibration run sets this
    baseline_total_score: float = 0.0
    iterations: list[PromptMutationOutcome] = field(default_factory=list)

    def run_iteration(
        self,
        mutation: PromptMutation,
        *,
        execute_fn: Callable[[str], tuple[str, Decimal]],
        corpus_terms: list[str],
        expected_claim_ids: list[str],
        rubric_judge_fn: Callable[[str], float],
    ) -> PromptMutationOutcome:
        """Run one mutation through the propose-execute-measure-gate
        loop.

        Args:
            mutation: the candidate prompt mutation
            execute_fn: takes a prompt, returns (synthesis_text, cost_usd).
                Wraps the dispatch call against the role's golden
                traces. Operator wires this against substrate.dispatch.
            corpus_terms: list of sector terms from the golden trace's
                corpus for the sector_vocab_overlap metric
            expected_claim_ids: claim_ids the synthesis should cite
            rubric_judge_fn: takes synthesis_text, returns rubric score
                in [0, 1]. The only LLM-judged component.

        Returns:
            PromptMutationOutcome with accept/reject decision.
        """
        _check_local_only()

        # Project cost before executing. The mutator can supply an
        # estimated cost in the mutation's rationale or metadata; for
        # the scaffold we trust the actual cost reported by execute_fn
        # after the fact.
        synthesis_text, cost_usd = execute_fn(mutation.proposed_prompt)
        try:
            self.budget.record_iteration_cost(cost_usd)
        except BudgetExceeded as exc:
            return PromptMutationOutcome(
                mutation_id=mutation.mutation_id,
                accepted=False,
                baseline_score=self.baseline_total_score,
                candidate_score=0.0,
                delta=0.0,
                epsilon_required=self.epsilon,
                composite_breakdown=CompositeScore(0, 0, 0, 0, 0),
                cost_usd=cost_usd,
                notes=f"budget exceeded: {exc}",
            )

        rubric = rubric_judge_fn(synthesis_text)
        cs = composite_score(
            synthesis_text,
            rubric_score=rubric,
            corpus_terms=corpus_terms,
            expected_claim_ids=expected_claim_ids,
        )
        delta = cs.total - self.baseline_total_score
        accepted = delta > self.epsilon

        outcome = PromptMutationOutcome(
            mutation_id=mutation.mutation_id,
            accepted=accepted,
            baseline_score=self.baseline_total_score,
            candidate_score=cs.total,
            delta=delta,
            epsilon_required=self.epsilon,
            composite_breakdown=cs,
            cost_usd=cost_usd,
        )
        self.iterations.append(outcome)

        if accepted:
            # Advance the baseline. The mutation's prompt text is now
            # the new baseline for subsequent iterations. Operator-side
            # commit of the prompt.py file lives outside the runner;
            # acceptance here is purely "the gate said yes."
            self.baseline_total_score = cs.total

        return outcome


def make_id() -> str:
    return f"mutation-{uuid.uuid4().hex[:12]}"
