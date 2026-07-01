"""Timeout-aware RLM iteration runner."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from interfaces.research.rlm_repl import ReplSummary

from .events import RLMEventEmitter
from .session import (
    RLM_REPL_PER_CALL_TIMEOUT_SECONDS,
    RLMSession,
    iteration_payload,
    session_completed_payload,
    session_failed_payload,
)


def _event_action_type(event: Any) -> str:
    action_type = event.action_type
    return str(action_type.value) if hasattr(action_type, "value") else str(action_type)


@dataclass(frozen=True)
class RLMIterationRun:
    status: Literal["iteration", "failed", "timeout", "cost_capped"]
    stdout: str | None
    event_action_type: str


@dataclass(frozen=True)
class RLMLoopRun:
    status: Literal["completed", "failed", "timeout", "cost_capped"]
    final_answer: str
    iterations: int
    event_action_type: str


IterationCost = Decimal | Callable[[ReplSummary, str], Decimal]
IterationSummary = str | Callable[[ReplSummary, str], str]


def _iteration_cost(cost_usd: IterationCost, summary: ReplSummary, code: str) -> Decimal:
    if callable(cost_usd):
        return cost_usd(summary, code)
    return cost_usd


def _iteration_summary(
    summary_template: IterationSummary,
    summary: ReplSummary,
    code: str,
) -> str:
    if callable(summary_template):
        return summary_template(summary, code)
    return summary_template


async def run_iteration_with_timeout(
    *,
    repl: Any,
    session: RLMSession,
    code: str,
    emitter: RLMEventEmitter,
    cost_usd: Decimal = Decimal("0.00"),
    timeout_s: float = float(RLM_REPL_PER_CALL_TIMEOUT_SECONDS),
    summary: str = "RLM iteration executed",
) -> RLMIterationRun:
    """Execute one generated-code iteration and emit the lifecycle event.

    This is the Sprint 11 long-document primitive: callers can use it inside a
    larger ``rlm_loop`` driver without hand-building events or forgetting the
    timeout/failure path.
    """

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(repl.execute, code)
    try:
        stdout = future.result(timeout=timeout_s)
    except FutureTimeoutError:
        executor.shutdown(wait=False, cancel_futures=True)
        session.fail()
        event = await emitter.emit(
            session_failed_payload(
                session,
                error_type="TimeoutError",
                error_message=f"RLM REPL execution exceeded {timeout_s:.3f}s",
            )
        )
        return RLMIterationRun(
            status="timeout",
            stdout=None,
            event_action_type=_event_action_type(event),
        )
    except Exception as exc:
        executor.shutdown(wait=True, cancel_futures=True)
        session.fail()
        event = await emitter.emit(
            session_failed_payload(
                session,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        )
        return RLMIterationRun(
            status="failed",
            stdout=None,
            event_action_type=_event_action_type(event),
        )
    else:
        executor.shutdown(wait=True, cancel_futures=True)

    repl_summary = repl.summarise()
    if repl_summary.exception:
        session.fail()
        event = await emitter.emit(
            session_failed_payload(
                session,
                error_type=str(repl_summary.exception).split(":", 1)[0],
                error_message=str(repl_summary.exception),
            )
        )
        return RLMIterationRun(
            status="failed",
            stdout=stdout,
            event_action_type=_event_action_type(event),
        )

    session.record_iteration(summary=summary, cost_usd=cost_usd)
    if session.state.status == "cost_capped":
        event = await emitter.emit(
            session_completed_payload(
                session,
                final_summary="RLM session stopped at the configured cost cap.",
            )
        )
        return RLMIterationRun(
            status="cost_capped",
            stdout=stdout,
            event_action_type=_event_action_type(event),
        )

    event = await emitter.emit(iteration_payload(session, session.iterations[-1]))
    return RLMIterationRun(
        status="iteration",
        stdout=stdout,
        event_action_type=_event_action_type(event),
    )


async def run_loop_with_timeout(
    *,
    repl: Any,
    generate_code: Callable[[ReplSummary], str],
    session: RLMSession,
    emitter: RLMEventEmitter,
    max_iterations: int | None = None,
    timeout_s: float = float(RLM_REPL_PER_CALL_TIMEOUT_SECONDS),
    cost_usd: IterationCost = Decimal("0.00"),
    iteration_summary: IterationSummary = "RLM iteration executed",
) -> RLMLoopRun:
    """Run an RLM REPL loop with timeout and typed lifecycle events."""

    limit = max_iterations or repl.max_iterations
    last_action_type = ""

    while not repl.is_finished() and repl.iteration < limit:
        repl_summary = repl.summarise()
        try:
            code = generate_code(repl_summary)
        except Exception as exc:
            session.fail()
            event = await emitter.emit(
                session_failed_payload(
                    session,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            return RLMLoopRun(
                status="failed",
                final_answer=repl.final_answer(),
                iterations=session.state.iteration_count,
                event_action_type=_event_action_type(event),
            )

        iteration = await run_iteration_with_timeout(
            repl=repl,
            session=session,
            code=code,
            emitter=emitter,
            cost_usd=_iteration_cost(cost_usd, repl_summary, code),
            timeout_s=timeout_s,
            summary=_iteration_summary(iteration_summary, repl_summary, code),
        )
        last_action_type = iteration.event_action_type
        if iteration.status in {"failed", "timeout", "cost_capped"}:
            return RLMLoopRun(
                status=iteration.status,
                final_answer=repl.final_answer(),
                iterations=session.state.iteration_count,
                event_action_type=last_action_type,
            )

    if not repl.answer.get("ready"):
        repl.answer["ready"] = True

    final_answer = repl.final_answer()
    session.complete(final_summary=final_answer)
    event = await emitter.emit(
        session_completed_payload(
            session,
            final_summary=final_answer,
        )
    )
    return RLMLoopRun(
        status="completed",
        final_answer=final_answer,
        iterations=session.state.iteration_count,
        event_action_type=_event_action_type(event),
    )


__all__ = [
    "RLMIterationRun",
    "RLMLoopRun",
    "run_iteration_with_timeout",
    "run_loop_with_timeout",
]
