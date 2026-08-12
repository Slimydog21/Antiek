"""RLM-3 — investigation_kind='rlm' orchestrator (rlm_integration_spec.md).

Per rlm_integration_spec.md RLM-3: ~500 LOC, net-new. A new
orchestration mode for investigations where the question is too
open-ended to decompose into 4-8 typed sub-questions in one shot.

Example: 'Survey the field of neutral-atom quantum computing' is
RLM-shape, not Loop-1-shape. The decomposer would either over-fan
(50 sub-questions) or under-fan (4 vague ones). The RLM
orchestrator walks the corpus + iteratively builds the decomposition
+ synthesis.

Sprint 19+ (RLM track, ratification-gated)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal

from .prime_agent_backend import (
    PrimeAgentOutcome,
    PrimeAgentRequest,
    PrimeAgentRLMBackend,
)
from .session import (
    RLMSession,
    create_session,
    iterate_session,
)

PRIME_EVIDENCE_LABEL = "[Supplemental Prime Agent evidence; non-canonical]"


@dataclass(frozen=True)
class RLMInvestigationConfig:
    """Per-investigation config for RLM mode."""

    investigation_id: str
    initial_question: str
    max_iterations: int = 10
    cost_cap_usd: Decimal = Decimal("5.00")


@dataclass(frozen=True)
class RLMIterationOutcome:
    """Outcome of one orchestration iteration."""

    iteration: int
    iteration_summary: str
    new_sub_questions: tuple[str, ...]
    cost_usd: Decimal
    should_continue: bool


def run_rlm_investigation(
    config: RLMInvestigationConfig,
    *,
    plan_iteration_fn: Callable[[str, list[str]], RLMIterationOutcome],
    final_synthesis_fn: Callable[[list[str]], tuple[str, Decimal]],
    prime_backend: PrimeAgentRLMBackend | None = None,
    prime_outcome_sink: Callable[[PrimeAgentOutcome], None] | None = None,
) -> tuple[str, RLMSession]:
    """Drive an RLM-mode investigation.

    plan_iteration_fn: takes (current_state_summary, accumulated_questions)
        and returns an RLMIterationOutcome.
    final_synthesis_fn: takes the accumulated answers and produces
        the final master synthesis + reports cost.

    Returns (final_synthesis_text, RLMSession)."""
    session = create_session(
        investigation_id=config.investigation_id,
        root_role="rlm_orchestrator",
    )

    accumulated_questions: list[str] = [config.initial_question]
    state_summary = "Initial state: starting from operator question"

    for i in range(config.max_iterations):
        outcome = plan_iteration_fn(state_summary, list(accumulated_questions))
        iterate_session(
            session,
            summary=f"Iteration {i+1}: {outcome.iteration_summary}",
            cost_usd=outcome.cost_usd,
        )
        if session.state.status == "cost_capped":
            break
        accumulated_questions.extend(outcome.new_sub_questions)
        state_summary = outcome.iteration_summary
        if not outcome.should_continue:
            break

    synthesis_inputs = list(accumulated_questions)
    if prime_backend is not None:
        with suppress(Exception):
            prime_outcome = prime_backend.run(PrimeAgentRequest(
                prompt="\n".join(accumulated_questions),
                workflow="rlm-investigation",
                request_id=f"{config.investigation_id}:investigation:final",
            ))
            if prime_outcome_sink is not None:
                with suppress(Exception):
                    prime_outcome_sink(prime_outcome)
            if (
                prime_outcome.receipt.state.value == "success"
                and prime_outcome.evidence is not None
                and prime_outcome.evidence.supplemental
            ):
                synthesis_inputs.append(
                    f"{PRIME_EVIDENCE_LABEL}\n{prime_outcome.evidence.text}"
                )

    final, final_cost = final_synthesis_fn(synthesis_inputs)
    iterate_session(session, summary="Final synthesis", cost_usd=final_cost)
    session.complete(final_summary=final)
    return (final, session)
