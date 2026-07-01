"""Timeout-aware RLM iteration runner."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

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


__all__ = ["RLMIterationRun", "run_iteration_with_timeout"]
