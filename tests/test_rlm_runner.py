"""Tests for the timeout-aware RLM iteration runner."""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal

from interfaces.research.rlm_repl import RLMRepl
from orchestration.rlm import (
    RLMEventEmitter,
    create_session,
    run_iteration_with_timeout,
)
from substrate.schemas.events import Event


def _emitter():
    seen: list[Event] = []

    async def broadcast(event: Event) -> None:
        seen.append(event)

    return RLMEventEmitter(
        broadcast,
        investigation_id="inv-rlm",
        document_id="doc-rlm",
        param_version="test-rlm",
    ), seen


def test_run_iteration_emits_iteration(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(
        investigation_id="inv-rlm",
        root_role="wrestler",
        document_id="doc-rlm",
    )
    emitter, seen = _emitter()
    repl = RLMRepl()

    result = asyncio.run(
        run_iteration_with_timeout(
            repl=repl,
            session=session,
            code="answer['content'] = 'partial'",
            emitter=emitter,
            cost_usd=Decimal("0.25"),
            timeout_s=1.0,
            summary="read chapter 2",
        )
    )

    assert result.status == "iteration"
    assert result.event_action_type == "rlm.iteration"
    assert session.state.iteration_count == 1
    assert session.state.cost_usd_accumulated == Decimal("0.25")
    assert len(seen) == 1
    assert seen[0].payload.action_type == "rlm.iteration"
    assert seen[0].payload.summary == "read chapter 2"


def test_run_iteration_timeout_emits_failure(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(investigation_id="inv-rlm", root_role="wrestler")
    emitter, seen = _emitter()

    class SlowRepl:
        def execute(self, code: str) -> str:
            time.sleep(0.05)
            return ""

        def summarise(self):  # pragma: no cover - timeout path never reaches this
            raise AssertionError("timed-out execution should not be summarized")

    result = asyncio.run(
        run_iteration_with_timeout(
            repl=SlowRepl(),
            session=session,
            code="while True: pass",
            emitter=emitter,
            timeout_s=0.001,
        )
    )

    assert result.status == "timeout"
    assert session.state.status == "failed"
    assert len(seen) == 1
    assert seen[0].payload.action_type == "rlm.session_failed"
    assert seen[0].payload.error_type == "TimeoutError"


def test_run_iteration_captured_repl_error_emits_failure(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(investigation_id="inv-rlm", root_role="wrestler")
    emitter, seen = _emitter()
    repl = RLMRepl()

    result = asyncio.run(
        run_iteration_with_timeout(
            repl=repl,
            session=session,
            code="answer['content'] = str(1 / 0)",
            emitter=emitter,
            timeout_s=1.0,
        )
    )

    assert result.status == "failed"
    assert session.state.status == "failed"
    assert len(seen) == 1
    assert seen[0].payload.action_type == "rlm.session_failed"
    assert seen[0].payload.error_type == "ZeroDivisionError"


def test_run_iteration_cost_cap_emits_completed(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(investigation_id="inv-rlm", root_role="wrestler")
    emitter, seen = _emitter()
    repl = RLMRepl()

    result = asyncio.run(
        run_iteration_with_timeout(
            repl=repl,
            session=session,
            code="x = 1",
            emitter=emitter,
            cost_usd=Decimal("5.01"),
            timeout_s=1.0,
        )
    )

    assert result.status == "cost_capped"
    assert session.state.status == "cost_capped"
    assert session.state.iteration_count == 0
    assert len(seen) == 1
    assert seen[0].payload.action_type == "rlm.session_completed"
    assert seen[0].payload.status == "cost_capped"
