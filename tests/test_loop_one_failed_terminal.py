"""A failed Loop One run writes its ``investigation.failed`` terminal (LB-3a0).

The thread contract reads a thread as failed only when the trajectory holds an
``investigation.failed`` row. ``InvestigationFailedPayload.phase`` is bounded to
1..9, so any failure path that reports ``phase=0`` raises a ValidationError
while building the payload. That happens inside the detached
``loop_one:<investigation_id>`` task, so the error never reaches a caller, no
terminal row lands, and the thread reads as running forever.

These tests drive the real start handler against a temp event log, await the
detached task, and read the trajectory back. Regression fixture:
``tests/regression/agent_failures/loop-one-failed-phase-zero-no-terminal.yaml``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from interfaces.research.api.broadcast import EventBroadcaster
from interfaces.research.api.research_owner_dispatch import PAID_LOOP_ONE_ROLES
from orchestration.loop_one import orchestrator
from orchestration.loop_one.coordinator import InvestigationCoordinator
from substrate.event_log import emit_typed, trajectory
from substrate.schemas import (
    ActionType,
    Event,
    InvestigationStartRequestedPayload,
)

_FAILED = ActionType.INVESTIGATION_FAILED.value
_COMPLETED = ActionType.INVESTIGATION_COMPLETED.value

_VALID_CHOICE = {
    "authority": "user_model",
    "provider_id": "provider-test",
    "model_id": "model-test",
}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    # The pre-phase-1 reuse probe is best-effort and irrelevant here; keep it
    # from loading embedders or reading the graph.
    import substrate.flywheel.investigation_start_reuse as reuse

    monkeypatch.setattr(
        reuse, "maybe_reuse_prior_knowledge_at_start", lambda **_: None,
    )


async def _start_and_await(
    investigation_id: str,
    payload: InvestigationStartRequestedPayload,
    *,
    owner_model_app: object | None = None,
) -> asyncio.Task[Any]:
    """Append a real start event, hand it to the Loop One start handler, and
    wait for the detached ``loop_one:<id>`` task to finish."""
    eid = emit_typed(investigation_id, payload, role="operator")
    assert eid is not None
    row = next(r for r in trajectory(investigation_id) if r["event_id"] == eid)
    event = Event.model_validate(row)

    broadcaster = EventBroadcaster()
    broadcaster._owner_model_app = owner_model_app
    handler = orchestrator.make_loop_one_handler(
        broadcaster, InvestigationCoordinator(broadcaster),
    )
    await handler(event)

    name = f"loop_one:{investigation_id}"
    tasks = [t for t in asyncio.all_tasks() if t.get_name() == name]
    assert len(tasks) == 1, f"expected one {name} task, found {len(tasks)}"
    task = tasks[0]
    await asyncio.wait([task], timeout=30)
    assert task.done(), f"{name} did not finish"
    return task


def _only_failed_row(investigation_id: str, task: asyncio.Task[Any]) -> dict:
    """The run ended in exactly one ``investigation.failed`` row, no
    ``investigation.completed`` row, and a task that did not raise."""
    rows = trajectory(investigation_id)
    failed = [r for r in rows if r["action_type"] == _FAILED]
    completed = [r for r in rows if r["action_type"] == _COMPLETED]
    exc = task.exception()
    assert exc is None and len(failed) == 1, (
        f"investigation.failed rows: {len(failed)}; loop_one task raised "
        f"{type(exc).__name__ if exc else None}: {exc}"
    )
    assert completed == []
    return failed[0]


# ---------------------------------------------------------------------------
# Owner-model refusals (investigation-start handler)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("app_present", "owner_user_id", "owner_operation_id", "choices"),
    [
        pytest.param(
            False, "user-1", "op-1",
            {role: dict(_VALID_CHOICE) for role in PAID_LOOP_ONE_ROLES},
            id="no-owner-model-app",
        ),
        pytest.param(
            True, None, "op-1",
            {role: dict(_VALID_CHOICE) for role in PAID_LOOP_ONE_ROLES},
            id="no-owner-user-id",
        ),
        pytest.param(
            True, "user-1", None,
            {role: dict(_VALID_CHOICE) for role in PAID_LOOP_ONE_ROLES},
            id="no-owner-operation-id",
        ),
        pytest.param(
            True, "user-1", "op-1",
            {
                role: {**_VALID_CHOICE, "authority": "platform"}
                for role in PAID_LOOP_ONE_ROLES
            },
            id="choice-fails-validation",
        ),
        pytest.param(
            True, "user-1", "op-1",
            {"decomposer": dict(_VALID_CHOICE)},
            id="choice-missing-a-paid-role",
        ),
    ],
)
async def test_owner_model_unavailable_writes_failed(
    monkeypatch, app_present, owner_user_id, owner_operation_id, choices,
):
    ran: list[str] = []

    async def _must_not_run(ctx, broadcaster, coordinator):
        ran.append(ctx.investigation_id)

    monkeypatch.setattr(orchestrator, "_run_investigation", _must_not_run)

    inv = "inv-lb3a0-owner"
    task = await _start_and_await(
        inv,
        InvestigationStartRequestedPayload(
            question="Does an owner-model refusal write its terminal?",
            owner_user_id=owner_user_id,
            owner_operation_id=owner_operation_id,
            owner_model_choices=choices,
        ),
        owner_model_app=object() if app_present else None,
    )

    row = _only_failed_row(inv, task)
    assert ran == [], "a refused owner-model launch must not start phase 1"
    payload = row["payload"]
    assert payload["phase"] == 1
    assert payload["reason"] == "owner_model_unavailable"
    assert payload["last_completed_phase"] is None
    assert row["policy_id"] == "owner-model-terminal"


# ---------------------------------------------------------------------------
# Phase loop: a phase returns False without naming itself
# ---------------------------------------------------------------------------


def _install_phases(monkeypatch, *, fail_at: int) -> None:
    """Replace the eight phase runners: phases before ``fail_at`` succeed and
    record themselves as completed; phase ``fail_at`` returns False without
    touching ``ctx.failed_phase``; later phases must never run."""

    def _make(position: int):
        async def _phase(ctx, *_args: Any) -> bool:
            if position < fail_at:
                ctx.last_completed_phase = position
                return True
            if position == fail_at:
                return False
            raise AssertionError(f"phase {position} ran after phase {fail_at} failed")

        return _phase

    for position in range(1, 9):
        monkeypatch.setattr(orchestrator, f"_run_phase_{position}", _make(position))


@pytest.mark.parametrize("fail_at", [1, 2, 8])
async def test_phase_false_without_failed_phase_writes_failed(monkeypatch, fail_at):
    _install_phases(monkeypatch, fail_at=fail_at)

    inv = f"inv-lb3a0-phase-{fail_at}"
    task = await _start_and_await(
        inv,
        InvestigationStartRequestedPayload(
            question="Does a silent phase failure write its terminal?",
        ),
    )

    payload = _only_failed_row(inv, task)["payload"]
    assert payload["phase"] == fail_at
    assert payload["reason"] == "(unknown)"
    assert payload["last_completed_phase"] == (fail_at - 1 if fail_at > 1 else None)


async def test_phase_that_names_itself_keeps_its_own_phase(monkeypatch):
    """A phase that sets ``failed_phase`` itself is reported as it said. The
    stub names phase 5 from loop position 2 on purpose, so the assertion can
    tell its own value apart from the position fallback."""

    async def _phase_1(ctx, *_args: Any) -> bool:
        ctx.last_completed_phase = 1
        return True

    async def _phase_2(ctx, *_args: Any) -> bool:
        ctx.failed_phase = 5
        ctx.fail_reason = "named failure"
        return False

    monkeypatch.setattr(orchestrator, "_run_phase_1", _phase_1)
    monkeypatch.setattr(orchestrator, "_run_phase_2", _phase_2)

    inv = "inv-lb3a0-named"
    task = await _start_and_await(
        inv, InvestigationStartRequestedPayload(question="Named failure?"),
    )

    payload = _only_failed_row(inv, task)["payload"]
    assert payload["phase"] == 5
    assert payload["reason"] == "named failure"
    assert payload["last_completed_phase"] == 1


async def test_silent_phase_failure_after_synthesis_does_not_chase(monkeypatch):
    """Phase 6 produced a synthesis, then phase 7 returned False without
    naming itself. The run failed, so the chase gate (synthesis present and
    no failed_phase) must not spawn a child."""

    def _make(position: int):
        async def _phase(ctx, *_args: Any) -> bool:
            if position == 7:
                return False
            if position == 6:
                ctx.synthesis = object()
            ctx.last_completed_phase = position
            return True

        return _phase

    for position in range(1, 9):
        monkeypatch.setattr(orchestrator, f"_run_phase_{position}", _make(position))
    chased: list[str] = []

    async def _record_chase(ctx, broadcaster):
        chased.append(ctx.investigation_id)

    monkeypatch.setattr(orchestrator, "_maybe_spawn_chase_child", _record_chase)

    inv = "inv-lb3a0-chase"
    task = await _start_and_await(
        inv,
        InvestigationStartRequestedPayload(
            question="Does a failed run chase?", chase_mode="depth", chase_value=3,
        ),
    )

    payload = _only_failed_row(inv, task)["payload"]
    assert payload["phase"] == 7
    assert payload["last_completed_phase"] == 6
    assert chased == [], "a failed run must not spawn a chase child"
