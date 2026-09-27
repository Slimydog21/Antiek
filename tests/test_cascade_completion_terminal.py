"""Every way the detached cascade completion task ends leaves a parent terminal.

``cascade_routes._run_to_completion`` drives a launched session through
``join_and_merge`` and then (maybe) the Loop 1 synthesis tail. The tail guards
its own cancel (``orchestrator._fail_on_cancel``), but the earlier join awaited
outside any guard: uvicorn cancelling the task at shutdown while
``runner.join`` waited raised ``CancelledError``, a BaseException the
``except Exception`` handler never sees, so the session parent's trajectory
kept no terminal and GET /investigations/{session_id} read ``in_progress``
forever. The same hole covered a join that RAISED: the failure was recorded as
``synthesis_tail_error`` but the parent still had no terminal.

These drive the real ``_run_to_completion`` over a real ``CascadeSession`` and
``HostLocalRunner``; only the gather loop and the tail runner are stand-ins.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from types import SimpleNamespace

import pytest
from starlette.requests import Request

import interfaces.research.api.cascade_routes as cr
from orchestration.cascade_session import (
    SYNTHESIS_TAIL_FAILED,
    CascadeSession,
    Leaf,
    ResearchState,
    SynthesisTailSkip,
    reconstruct_session,
)
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.cascade_planner import SubQuestion, approve_plan, build_plan, persist_tree
from roles.cascade_planner.persist import load_tree
from runtime.research_runner import (
    BudgetCap,
    Command,
    CommandKind,
    HostLocalRunner,
    PromotionFunnel,
    RunState,
    terminal_event,
)
from substrate.event_log import log_event, trajectory
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import ActionType

_LIFECYCLE = (ActionType.INVESTIGATION_COMPLETED.value, ActionType.INVESTIGATION_FAILED.value)


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class _Dec:
    def decompose(self, q: str, *, context: str = ""):
        return [SubQuestion(question="sub one"), SubQuestion(question="sub two")]


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture(autouse=True)
def _restore_runner():
    saved = cr._SYNTHESIS_TAIL_RUNNER
    yield
    cr.set_synthesis_tail_runner(saved)


@pytest.fixture
def env(monkeypatch):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "g.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    import substrate.graph.insight_question as iq

    monkeypatch.setattr(iq, "graph_db_path", lambda: db)
    init_database_at_path(db)
    return {"db": db, "events": ev}


def _slow_loop():
    """A gather that stays in flight until something ends it."""

    async def _loop(ctx):
        for i in range(10_000):
            sub_q = await ctx.checkpoint()
            await asyncio.sleep(0.01)
            yield ctx.step(f"pass {i} on {sub_q}", cost_usd=0.0, tokens=0)

    return _loop


def _finished_loop():
    async def _loop(ctx):
        sub_q = await ctx.checkpoint()
        yield ctx.step(f"one pass on {sub_q}", cost_usd=0.0, tokens=0)

    return _loop


def _approved_root(env, session_id: str) -> str:
    tree = build_plan("the problem", decomposer=_Dec()).tree
    root_id = persist_tree(
        tree, investigation_id=session_id,
        embedding_provider=_FakeEmbedding(), db_path=env["db"],
    )
    approve_plan(root_id, approver="operator", investigation_id=session_id, db_path=env["db"])
    return root_id


async def _launched(env, loop, session_id="session-ct", budget: BudgetCap | None = None):
    root_id = _approved_root(env, session_id)
    leaves = [
        Leaf(investigation_id=f"{session_id}-leaf-{i}", sub_question=c.question,
             question_node_id=c.graph_node_id, budget=budget or BudgetCap())
        for i, c in enumerate(load_tree(root_id, db_path=env["db"]).root.children)
    ]
    funnel = PromotionFunnel(db_path=env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(loop, events_dir=env["events"], seal_on_complete=False,
                             on_emit=funnel.submit)
    session = CascadeSession(session_id, runner=runner, funnel=funnel,
                             events_dir=env["events"], db_path=env["db"])
    await session.launch(root_id, leaves)
    return session


async def _until(predicate, timeout=10.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    pytest.fail("condition never held")


def _parent_lifecycle(session, env) -> list[dict]:
    return [r for r in trajectory(session.session_id, events_dir=env["events"])
            if r["action_type"] in _LIFECYCLE]


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


async def _live_status(session) -> dict:
    cr._SESSIONS[session.session_id] = session
    try:
        return await cr.session_status(session.session_id, _request())
    finally:
        cr._SESSIONS.pop(session.session_id, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("tail_wired", [True, False], ids=["tail-wired", "no-tail"])
async def test_cancel_during_join_writes_a_failed_parent_terminal(env, tail_wired):
    tail_calls: list[str] = []

    async def _tail(_session, _pack):
        tail_calls.append("called")

    cr.set_synthesis_tail_runner(_tail if tail_wired else None)
    session = await _launched(env, _slow_loop())
    await _until(lambda: all(s.state == RunState.RUNNING.value for s in session.status()))

    task = asyncio.create_task(cr._run_to_completion(session))
    await asyncio.sleep(0.05)  # the task is now parked in runner.join()
    assert not task.done()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()  # the cancellation still propagates

    rows = _parent_lifecycle(session, env)
    assert [r["action_type"] for r in rows] == [ActionType.INVESTIGATION_FAILED.value], rows
    reason = rows[0]["payload"]["reason"]
    assert "cancelled" in reason and "join_and_merge" in reason, reason
    state, _row = terminal_event(trajectory(session.session_id, events_dir=env["events"]))
    assert state is RunState.FAILED
    assert tail_calls == []
    assert session.synthesis_tail_error is not None
    assert session.synthesis_tail_error.startswith("[join_and_merge] CancelledError")

    status = await _live_status(session)
    assert status["deep_research_complete"] is False
    assert status["parent_terminal"]["state"] == "failed"
    rec = reconstruct_session(session.session_id, events_dir=env["events"])
    assert rec.parent_terminal is not None and rec.parent_terminal["state"] == "failed"
    assert rec.synthesis_tail_error is not None


@pytest.mark.asyncio
async def test_a_join_that_raises_writes_a_failed_parent_terminal(env, monkeypatch):
    cr.set_synthesis_tail_runner(None)
    session = await _launched(env, _finished_loop())

    async def _boom():
        raise RuntimeError("funnel drain exploded")

    monkeypatch.setattr(session, "join_and_merge", _boom)
    await cr._run_to_completion(session)  # non-fatal

    rows = _parent_lifecycle(session, env)
    assert [r["action_type"] for r in rows] == [ActionType.INVESTIGATION_FAILED.value], rows
    assert "funnel drain exploded" in rows[0]["payload"]["reason"]
    assert (await _live_status(session))["parent_terminal"]["state"] == "failed"
    await session._runner.join()


@pytest.mark.asyncio
async def test_cancel_inside_a_tail_that_wrote_no_terminal_writes_one(env):
    """The tail runner is a seam: a runner that is cancelled before writing its
    own terminal (anything other than the guarded Loop 1 tail) must not leave
    the parent open either."""
    started = asyncio.Event()

    async def _hanging_tail(_session, _pack):
        started.set()
        await asyncio.Event().wait()

    cr.set_synthesis_tail_runner(_hanging_tail)
    session = await _launched(env, _finished_loop())
    # The skip gate needs a done leaf with a citable chunk; this test is about
    # the cancel, so let the tail run.
    session.synthesis_tail_skip = lambda _pack: None  # type: ignore[method-assign]
    task = asyncio.create_task(cr._run_to_completion(session))
    await asyncio.wait_for(started.wait(), timeout=10.0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()

    rows = _parent_lifecycle(session, env)
    assert [r["action_type"] for r in rows] == [ActionType.INVESTIGATION_FAILED.value], rows
    assert "synthesis_tail" in rows[0]["payload"]["reason"]


@pytest.mark.asyncio
async def test_a_tail_that_wrote_its_own_terminal_is_not_overwritten(env):
    """The guarded Loop 1 tail writes ``investigation.failed`` itself on cancel;
    the completion guard must add nothing (one terminal, the tail's)."""
    started = asyncio.Event()

    async def _guarded_tail(session, _pack):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            log_event(session.session_id, ActionType.INVESTIGATION_FAILED,
                      payload={"phase": 6, "reason": "cancelled during phase 6",
                               "last_completed_phase": None},
                      role="orchestrator", events_dir=env["events"])
            raise

    cr.set_synthesis_tail_runner(_guarded_tail)
    session = await _launched(env, _finished_loop())
    session.synthesis_tail_skip = lambda _pack: None  # type: ignore[method-assign]
    task = asyncio.create_task(cr._run_to_completion(session))
    await asyncio.wait_for(started.wait(), timeout=10.0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    rows = _parent_lifecycle(session, env)
    assert len(rows) == 1, rows
    assert rows[0]["payload"]["reason"] == "cancelled during phase 6"


@pytest.mark.asyncio
async def test_completion_running_tracks_the_background_task(env):
    """A session whose completion never writes a parent terminal (no tail wired,
    or a hard-ceiling run) must still tell a poller when nothing more is coming."""
    cr.set_synthesis_tail_runner(None)
    session = await _launched(env, _finished_loop(), session_id="session-cr")
    task = asyncio.create_task(cr._run_to_completion(session))
    cr._SESSION_TASKS[session.session_id] = task
    try:
        assert (await _live_status(session))["completion_running"] is True
        await task
        status = await _live_status(session)
        assert status["completion_running"] is False
        assert status["parent_terminal"] is None
    finally:
        cr._SESSION_TASKS.pop(session.session_id, None)


async def _stop_leaves(session) -> None:
    for s in session.status():
        if not RunState(s.state).is_terminal():
            await session.steer(s.investigation_id, Command(kind=CommandKind.STOP))
    await session._runner.join()


@pytest.mark.asyncio
async def test_cancel_before_the_completion_task_starts_writes_a_failed_parent_terminal(
    env, monkeypatch,
):
    """Shutdown can cancel the detached task before its first step. A coroutine
    cancelled then never enters its body, so neither its cancel handler nor its
    ``finally`` ran: the parent kept no terminal and the hard-ceiling execution
    stayed open. Drive the real launch route and cancel the task it scheduled
    before the event loop runs it."""
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", env["db"])
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _FakeEmbedding())
    monkeypatch.setattr(cr, "_reuse_substrate", lambda *_a, **_k: None)
    monkeypatch.setattr(cr, "_research_loop_factory", lambda **_kw: _slow_loop())
    tail_calls: list[str] = []

    async def _tail(_session, _pack):
        tail_calls.append("called")

    cr.set_synthesis_tail_runner(_tail)
    root_id = _approved_root(env, "session-plan")
    resp = await cr.launch(root_id, cr.LaunchRequest(), _request())
    sid = resp["session_id"]
    session = cr._SESSIONS[sid]
    task = cr._SESSION_TASKS[sid]
    closed: list[str] = []
    ledger = SimpleNamespace(close_execution=lambda _key, run_id, _why: closed.append(run_id))
    cr._HARD_CEILING_RUNS[session] = (
        SimpleNamespace(ledger=ledger), SimpleNamespace(run_id="run-1"),
    )
    cr._OWNER_CASCADE_LAUNCHES[sid] = SimpleNamespace(manifest=None)
    try:
        assert not task.done()
        task.cancel()  # lands before the task's first step
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled()

        rows = _parent_lifecycle(session, env)
        assert [r["action_type"] for r in rows] == [ActionType.INVESTIGATION_FAILED.value], rows
        assert "cancelled" in rows[0]["payload"]["reason"]
        state, _row = terminal_event(trajectory(sid, events_dir=env["events"]))
        assert state is RunState.FAILED
        assert tail_calls == []
        # The cleanup the task's ``finally`` would have done still happens.
        assert closed == ["run-1"]
        assert sid not in cr._OWNER_CASCADE_LAUNCHES
        cr._HARD_CEILING_RUNS.pop(session, None)
        status = await cr.session_status(sid, _request())
        assert status["parent_terminal"]["state"] == "failed"
        assert status["completion_running"] is False
    finally:
        cr._HARD_CEILING_RUNS.pop(session, None)
        cr._OWNER_CASCADE_LAUNCHES.pop(sid, None)
        cr._SESSIONS.pop(sid, None)
        cr._SESSION_TASKS.pop(sid, None)
        cr._SESSION_SOURCE_POLICIES.pop(sid, None)
        await _stop_leaves(session)


@pytest.mark.asyncio
async def test_a_cancel_after_the_task_ran_is_recorded_once(env):
    """The unstarted-task guard must not add a second terminal or a second
    failure record when the body already handled its own cancel."""
    cr.set_synthesis_tail_runner(None)
    session = await _launched(env, _slow_loop(), session_id="session-once")
    await _until(lambda: all(s.state == RunState.RUNNING.value for s in session.status()))
    task = cr._schedule_completion(session)
    await asyncio.sleep(0.05)
    assert not task.done()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)  # let the done callbacks run

    rows = _parent_lifecycle(session, env)
    assert [r["action_type"] for r in rows] == [ActionType.INVESTIGATION_FAILED.value], rows
    failures = [r for r in trajectory(session.session_id, events_dir=env["events"])
                if r["action_type"] == SYNTHESIS_TAIL_FAILED]
    assert len(failures) == 1, failures
    await _stop_leaves(session)


@pytest.mark.asyncio
async def test_every_leaf_budget_halted_ends_the_parent_budget_halted_not_stopped(env):
    """No leaf finished because the budget halted each one: that is the
    budget's verdict, not an operator stop, so the parent must not read
    ``stopped``."""
    tail_calls: list[str] = []

    async def _tail(_session, _pack):
        tail_calls.append("called")

    cr.set_synthesis_tail_runner(_tail)
    async def _overspending(ctx):
        sub_q = await ctx.checkpoint()
        yield ctx.step(f"costly pass on {sub_q}", cost_usd=1.0, tokens=1)
        await asyncio.Event().wait()  # never finishes on its own

    session = await _launched(env, _overspending, session_id="session-bh",
                              budget=BudgetCap(cost_usd=0.5))
    await cr._run_to_completion(session)

    assert {s.state for s in session.status()} == {RunState.BUDGET_HALTED.value}
    assert tail_calls == []
    assert session.synthesis_tail_skipped is SynthesisTailSkip.NO_LEAF_DONE
    # Neither ``completed`` (outcome stopped) nor ``failed``.
    assert _parent_lifecycle(session, env) == []
    state, row = terminal_event(trajectory(session.session_id, events_dir=env["events"]))
    assert state is RunState.BUDGET_HALTED
    assert "2 of 2 budget-halted" in row["payload"]["reason"]
    status = await _live_status(session)
    assert status["parent_terminal"]["state"] == "budget_halted"
    rec = reconstruct_session(session.session_id, events_dir=env["events"])
    assert rec.parent_terminal is not None and rec.parent_terminal["state"] == "budget_halted"


def _states(*states: str) -> list[ResearchState]:
    return [ResearchState(f"leaf-{i}", f"sub {i}", st) for i, st in enumerate(states)]


@pytest.mark.parametrize(
    ("states", "action", "fragment"),
    [
        (("stopped", "stopped"), ActionType.INVESTIGATION_COMPLETED, None),
        (("stopped", "budget_halted"), ActionType.INVESTIGATION_CHASE_HALTED,
         "1 of 2 budget-halted"),
        (("failed", "stopped"), ActionType.INVESTIGATION_FAILED, "1 of 2 failed (leaf-0)"),
        (("failed", "budget_halted"), ActionType.INVESTIGATION_FAILED, "1 of 2 failed"),
        (("pending", "stopped"), ActionType.INVESTIGATION_FAILED,
         "never ended (leaf-0=pending)"),
        ((), ActionType.INVESTIGATION_FAILED, "no leaf research ran"),
    ],
    ids=["all-stopped", "stopped+halted", "failed+stopped", "failed+halted", "unended", "empty"],
)
def test_no_leaf_done_parent_terminal_follows_the_leaf_outcomes(states, action, fragment):
    """Stopped only when the operator stopped every leaf; anything that failed
    or never ended fails the parent; a budget halt is its own terminal."""
    from orchestration.cascade_session import _no_leaf_done_terminal

    got_action, payload = _no_leaf_done_terminal(_states(*states))
    assert got_action is action
    if fragment is None:
        assert payload == {"outcome": "stopped"}
    else:
        assert fragment in payload["reason"], payload
    expected = {
        ActionType.INVESTIGATION_COMPLETED: RunState.STOPPED,
        ActionType.INVESTIGATION_CHASE_HALTED: RunState.BUDGET_HALTED,
        ActionType.INVESTIGATION_FAILED: RunState.FAILED,
    }[action]
    terminal = terminal_event([{"action_type": got_action.value, "payload": payload}])
    assert terminal is not None and terminal[0] is expected
