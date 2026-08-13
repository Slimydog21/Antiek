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

import json
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .prime_agent_backend import (
    PrimeAgentOutcome,
    PrimeAgentRequest,
    PrimeAgentRLMBackend,
    PrimeAgentSessionRequest,
)
from .session import (
    RLMSession,
    create_session,
    iterate_session,
)

PRIME_EVIDENCE_LABEL = "[Supplemental Prime Agent evidence; non-canonical]"
_PRIME_ENABLED_ENV = "ANTIEK_PRIME_AGENT_RLM_ENABLED"


@dataclass(frozen=True)
class RLMInvestigationConfig:
    """Per-investigation config for RLM mode."""

    investigation_id: str
    initial_question: str
    max_iterations: int = 10
    cost_cap_usd: Decimal = Decimal("5.00")
    driver: str = "dispatch"


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
    prime_agent_backend: PrimeAgentRLMBackend | None = None,
    prime_outcome_sink: Callable[[PrimeAgentOutcome], None] | None = None,
) -> tuple[str, RLMSession]:
    """Drive an RLM-mode investigation.

    plan_iteration_fn: takes (current_state_summary, accumulated_questions)
        and returns an RLMIterationOutcome.
    final_synthesis_fn: takes the accumulated answers and produces
        the final master synthesis + reports cost.

    Returns (final_synthesis_text, RLMSession)."""
    driver = _normalize_driver(config.driver)
    resolved_prime_backend = _resolve_prime_backend(
        prime_backend=prime_backend,
        prime_agent_backend=prime_agent_backend,
    )
    if driver == "prime_agent":
        if not _prime_agent_enabled():
            raise ValueError(
                "prime_agent driver requires ANTIEK_PRIME_AGENT_RLM_ENABLED=1"
            )
        if resolved_prime_backend is None:
            raise ValueError("prime_agent driver requires prime_agent_backend")

    session = create_session(
        investigation_id=config.investigation_id,
        root_role="rlm_orchestrator",
        root_executor=driver,
        prime_goal_brief=(
            _prime_goal_brief(config)
            if driver == "prime_agent"
            else None
        ),
    )

    accumulated_questions: list[str] = [config.initial_question]
    state_summary = "Initial state: starting from operator question"

    for i in range(config.max_iterations):
        outcome = _plan_iteration(
            driver=driver,
            config=config,
            iteration_index=i,
            state_summary=state_summary,
            accumulated_questions=accumulated_questions,
            plan_iteration_fn=plan_iteration_fn,
            prime_backend=resolved_prime_backend,
            prime_outcome_sink=prime_outcome_sink,
            goal_brief=session.state.prime_goal_brief,
        )
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
    if resolved_prime_backend is not None:
        with suppress(Exception):
            prime_outcome = resolved_prime_backend.run(PrimeAgentRequest(
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


def _normalize_driver(value: str) -> str:
    driver = value.strip().lower() or "dispatch"
    if driver not in {"dispatch", "prime_agent"}:
        raise ValueError(f"unsupported rlm investigation driver: {value!r}")
    return driver


def _resolve_prime_backend(
    *,
    prime_backend: PrimeAgentRLMBackend | None,
    prime_agent_backend: PrimeAgentRLMBackend | None,
) -> PrimeAgentRLMBackend | None:
    if (
        prime_backend is not None
        and prime_agent_backend is not None
        and prime_backend is not prime_agent_backend
    ):
        raise ValueError(
            "prime_backend and prime_agent_backend refer to different backends"
        )
    return prime_agent_backend if prime_agent_backend is not None else prime_backend


def _prime_agent_enabled() -> bool:
    return os.environ.get(_PRIME_ENABLED_ENV, "") == "1"


def _prime_goal_brief(config: RLMInvestigationConfig) -> str:
    return (
        "You are the Antiek RLM-3 iteration planner. "
        "Return JSON with fields iteration_summary (str), "
        "new_sub_questions (list[str]), cost_usd (decimal string), "
        "should_continue (bool)."
        f" Investigation={config.investigation_id}."
        f" Initial question={config.initial_question}."
    )


def _plan_iteration(
    *,
    driver: str,
    config: RLMInvestigationConfig,
    iteration_index: int,
    state_summary: str,
    accumulated_questions: list[str],
    plan_iteration_fn: Callable[[str, list[str]], RLMIterationOutcome],
    prime_backend: PrimeAgentRLMBackend | None,
    prime_outcome_sink: Callable[[PrimeAgentOutcome], None] | None,
    goal_brief: str | None,
) -> RLMIterationOutcome:
    if driver != "prime_agent" or prime_backend is None or not goal_brief:
        return plan_iteration_fn(state_summary, list(accumulated_questions))

    request = PrimeAgentSessionRequest(
        goal_brief=goal_brief,
        iteration_prompt=_render_prime_iteration_prompt(
            config=config,
            iteration_index=iteration_index,
            state_summary=state_summary,
            accumulated_questions=accumulated_questions,
        ),
        workflow="rlm-investigation-iteration",
        request_id=f"{config.investigation_id}:iteration:{iteration_index + 1}",
    )
    outcome = prime_backend.run_session(request)
    if prime_outcome_sink is not None:
        with suppress(Exception):
            prime_outcome_sink(outcome)

    parsed = _parse_prime_iteration_outcome(
        evidence_text=(outcome.evidence.text if outcome.evidence is not None else None),
        fallback_iteration=iteration_index + 1,
    )
    if parsed is not None:
        return parsed
    return plan_iteration_fn(state_summary, list(accumulated_questions))


def _render_prime_iteration_prompt(
    *,
    config: RLMInvestigationConfig,
    iteration_index: int,
    state_summary: str,
    accumulated_questions: list[str],
) -> str:
    joined_questions = "\n".join(f"- {question}" for question in accumulated_questions)
    return (
        f"investigation_id: {config.investigation_id}\n"
        f"iteration: {iteration_index + 1}\n"
        f"state_summary: {state_summary}\n"
        "accumulated_questions:\n"
        f"{joined_questions}\n"
    )


def _parse_prime_iteration_outcome(
    *,
    evidence_text: str | None,
    fallback_iteration: int,
) -> RLMIterationOutcome | None:
    if evidence_text is None:
        return None
    try:
        payload = json.loads(evidence_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    summary = payload.get("iteration_summary")
    if not isinstance(summary, str) or not summary.strip():
        return None

    raw_questions = payload.get("new_sub_questions", [])
    if not isinstance(raw_questions, list):
        return None
    new_questions = tuple(str(item) for item in raw_questions)

    raw_should_continue = payload.get("should_continue")
    if not isinstance(raw_should_continue, bool):
        return None

    raw_cost = payload.get("cost_usd", "0")
    try:
        cost_usd = Decimal(str(raw_cost))
    except (InvalidOperation, ValueError):
        return None
    if cost_usd < 0:
        return None

    raw_iteration = payload.get("iteration", fallback_iteration)
    try:
        iteration = int(raw_iteration)
    except (TypeError, ValueError):
        iteration = fallback_iteration

    return RLMIterationOutcome(
        iteration=iteration,
        iteration_summary=summary,
        new_sub_questions=new_questions,
        cost_usd=cost_usd,
        should_continue=raw_should_continue,
    )
