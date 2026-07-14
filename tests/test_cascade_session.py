"""ANT-DRL P-13 — cascade_session reconstruct + DeepResearchComplete guard.

Hermetic gates for PLATFORM_EXEC_MATRIX row P-13 and split-brain negative
coverage paired with P-12.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from orchestration.cascade_session import CascadeSession, Leaf, reconstruct_session
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.cascade_planner import (
    SubQuestion,
    approve_plan,
    build_plan,
    persist_tree,
)
from roles.cascade_planner.persist import load_tree
from runtime.research_runner import (
    Handle,
    HostLocalRunner,
    PromotionFunnel,
    RunState,
    make_demo_loop,
)
from substrate.graph.schema import init_database_at_path


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class _Dec:
    def __init__(self, subs: list[str]) -> None:
        self._subs = subs

    def decompose(self, q: str, *, context: str = ""):
        return [SubQuestion(question=s) for s in self._subs]


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


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


def _approved_plan(env, subs=("sub one", "sub two")):
    tree = build_plan("the problem", decomposer=_Dec(list(subs))).tree
    root_id = persist_tree(
        tree,
        investigation_id="session-1",
        embedding_provider=_FakeEmbedding(),
        db_path=env["db"],
    )
    approve_plan(
        root_id,
        approver="operator",
        investigation_id="session-1",
        db_path=env["db"],
    )
    loaded = load_tree(root_id, db_path=env["db"])
    leaves = [
        Leaf(
            investigation_id=f"leaf-{i}",
            sub_question=c.question,
            question_node_id=c.graph_node_id,
        )
        for i, c in enumerate(loaded.root.children)
    ]
    return root_id, leaves


def _make_session(env):
    funnel = PromotionFunnel(db_path=env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        make_demo_loop(steps=2, emit_note=True),
        events_dir=env["events"],
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    return CascadeSession(
        "session-1",
        runner=runner,
        funnel=funnel,
        events_dir=env["events"],
        db_path=env["db"],
    )


async def _drain(session: CascadeSession):
    return [ev async for ev in session.stream()]


@pytest.mark.asyncio
async def test_session_reconstructs_from_event_log(env):
    """P-13: membership + terminal state recoverable from JSONL alone."""
    root_id, leaves = _approved_plan(env, subs=["a", "b", "c"])
    session = _make_session(env)
    await session.launch(root_id, leaves)
    await _drain(session)
    await session.join_and_merge()

    recovery = reconstruct_session("session-1", events_dir=env["events"])
    assert {r.investigation_id for r in recovery.researches} == {
        "leaf-0",
        "leaf-1",
        "leaf-2",
    }
    assert recovery.all_terminal
    assert all(r.state == RunState.DONE.value for r in recovery.researches)
    assert recovery.plan_root_node_id == root_id
    assert {
        r.investigation_id: r.question_node_id for r in recovery.researches
    } == {
        leaf.investigation_id: leaf.question_node_id for leaf in leaves
    }


@pytest.mark.asyncio
async def test_recovery_never_carries_mapping_across_launch_receipts(env):
    """A later legacy/malformed relaunch cannot inherit the prior map."""
    from substrate.event_log import log_event

    root_id, leaves = _approved_plan(env, subs=["a"])
    session = _make_session(env)
    loaded = load_tree(root_id, db_path=env["db"])
    await session.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    await _drain(session)

    log_event(
        "session-1",
        "cascade.launched",
        payload={
            "plan_root_node_id": "new-root",
            "leaf_count": 1,
            "launch_generation": (session.launch_generation or 0) + 1,
        },
        role="user_agent",
        events_dir=env["events"],
    )
    recovery = reconstruct_session("session-1", events_dir=env["events"])
    assert recovery.plan_root_node_id == "new-root"
    assert recovery.approved_plan_tree is None
    assert all(r.question_node_id is None for r in recovery.researches)
    assert all(r.plan_node_local_id is None for r in recovery.researches)
    assert all(r.state == RunState.PENDING.value for r in recovery.researches)


@pytest.mark.asyncio
async def test_relaunch_start_supersedes_the_prior_terminal_generation(env):
    root_id, leaves = _approved_plan(env, subs=["a"])
    loaded = load_tree(root_id, db_path=env["db"])
    first = _make_session(env)
    await first.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    await _drain(first)
    await first.join_and_merge()
    first.record_session_terminal()
    assert reconstruct_session("session-1", events_dir=env["events"]).all_terminal

    second = _make_session(env)
    await second.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    recovery = reconstruct_session("session-1", events_dir=env["events"])
    assert recovery.researches[0].state == RunState.PENDING.value
    await _drain(second)


@pytest.mark.asyncio
async def test_recovery_generation_is_independent_of_wall_clock(env, monkeypatch):
    import orchestration.cascade_session as cascade_module

    root_id, leaves = _approved_plan(env, subs=["a"])
    loaded = load_tree(root_id, db_path=env["db"])
    first = _make_session(env)
    await first.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    await _drain(first)
    await first.join_and_merge()
    first.record_session_terminal()

    second = _make_session(env)
    await second.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    original_trajectory = cascade_module.trajectory

    def skewed_trajectory(investigation_id, *, events_dir=None):
        rows = original_trajectory(investigation_id, events_dir=events_dir)
        skewed = []
        for row in rows:
            copy = dict(row)
            payload = copy.get("payload", {})
            generation = payload.get("launch_generation") if isinstance(payload, dict) else None
            if generation is None and isinstance(payload, dict):
                generation = payload.get("cascade_launch_generation")
            copy["emitted_at"] = "1900-01-01T00:00:00Z" if generation == 2 else "2999-01-01T00:00:00Z"
            skewed.append(copy)
        return sorted(skewed, key=lambda row: row["emitted_at"])

    monkeypatch.setattr(cascade_module, "trajectory", skewed_trajectory)
    recovered = reconstruct_session("session-1", events_dir=env["events"])
    assert recovered.researches[0].state == RunState.PENDING.value
    assert recovered.plan_root_node_id == root_id
    await _drain(second)


@pytest.mark.asyncio
async def test_relaunch_does_not_inherit_prior_synthesis_failure(env):
    root_id, leaves = _approved_plan(env, subs=["a"])
    loaded = load_tree(root_id, db_path=env["db"])
    first = _make_session(env)
    await first.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    await _drain(first)
    await first.join_and_merge()
    first.record_synthesis_tail_error(RuntimeError("old generation failed"))
    assert "old generation failed" in (
        reconstruct_session(
            "session-1", events_dir=env["events"]
        ).synthesis_tail_error or ""
    )
    first.record_session_terminal()

    second = _make_session(env)
    await second.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    assert reconstruct_session(
        "session-1", events_dir=env["events"]
    ).synthesis_tail_error is None
    await _drain(second)


@pytest.mark.asyncio
async def test_partial_runner_start_never_emits_a_complete_launch_receipt(env):
    from substrate.event_log import trajectory

    root_id, leaves = _approved_plan(env, subs=["a", "b"])
    session = _make_session(env)
    original_start = session._runner.start
    calls = 0

    async def fail_second(investigation_id, plan):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second runner did not start")
        return await original_start(investigation_id, plan)

    session._runner.start = fail_second
    with pytest.raises(RuntimeError, match="second runner"):
        await session.launch(root_id, leaves, approved_plan_tree={"root": {}})
    assert session._handles == {}
    assert session._pump_tasks == []
    assert session._runner.status(Handle("leaf-0")).state.is_terminal()
    assert not any(
        event.get("action_type") == "cascade.launched"
        for event in trajectory("session-1", events_dir=env["events"])
    )
    assert reconstruct_session("session-1", events_dir=env["events"]).researches == []


@pytest.mark.asyncio
async def test_launch_receipt_failure_cleans_up_every_started_runner(env, monkeypatch):
    import orchestration.cascade_session as cascade_module

    root_id, leaves = _approved_plan(env, subs=["a"])
    session = _make_session(env)
    original_log_event = cascade_module.log_event

    def fail_receipt(investigation_id, action_type, **kwargs):
        if action_type == "cascade.launched":
            raise OSError("event store unavailable")
        return original_log_event(investigation_id, action_type, **kwargs)

    monkeypatch.setattr("orchestration.cascade_session.log_event", fail_receipt)
    with pytest.raises(OSError, match="event store"):
        await session.launch(root_id, leaves, approved_plan_tree={"root": {}})
    assert session._handles == {}
    assert session._pump_tasks == []
    assert session.plan_root_node_id is None
    assert session._runner.status(Handle("leaf-0")).state.is_terminal()


@pytest.mark.asyncio
async def test_silently_dropped_launch_receipt_rolls_back(env, monkeypatch):
    import orchestration.cascade_session as cascade_module

    root_id, leaves = _approved_plan(env, subs=["a"])
    session = _make_session(env)
    original_log_event = cascade_module.log_event

    def drop_receipt(investigation_id, action_type, **kwargs):
        if action_type == "cascade.launched":
            return None
        return original_log_event(investigation_id, action_type, **kwargs)

    monkeypatch.setattr("orchestration.cascade_session.log_event", drop_receipt)

    with pytest.raises(RuntimeError, match="was not persisted exactly"):
        await session.launch(root_id, leaves, approved_plan_tree={"root": {}})
    assert session._handles == {}
    assert session._runner.status(Handle("leaf-0")).state.is_terminal()


@pytest.mark.asyncio
async def test_failed_attempt_consumes_generation_before_retry(env):
    root_id, leaves = _approved_plan(env, subs=["a", "b"])
    failed = _make_session(env)
    original_start = failed._runner.start
    calls = 0

    async def fail_second(investigation_id, plan):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second start failed")
        return await original_start(investigation_id, plan)

    failed._runner.start = fail_second
    with pytest.raises(RuntimeError, match="second start"):
        await failed.launch(root_id, leaves, approved_plan_tree={"root": {}})

    retried = _make_session(env)
    loaded = load_tree(root_id, db_path=env["db"])
    await retried.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    assert retried.launch_generation == 2
    recovered = reconstruct_session("session-1", events_dir=env["events"])
    assert all(research.state == RunState.PENDING.value for research in recovered.researches)
    await _drain(retried)


@pytest.mark.asyncio
async def test_receipt_verification_rejects_matching_id_with_corrupt_content(env, monkeypatch):
    import orchestration.cascade_session as cascade_module

    root_id, leaves = _approved_plan(env, subs=["a"])
    session = _make_session(env)
    original_log_event = cascade_module.log_event

    def corrupt_receipt(investigation_id, action_type, **kwargs):
        if action_type == "cascade.launched":
            kwargs["payload"] = {"launch_generation": 1}
        return original_log_event(investigation_id, action_type, **kwargs)

    monkeypatch.setattr("orchestration.cascade_session.log_event", corrupt_receipt)
    with pytest.raises(RuntimeError, match="persisted exactly"):
        await session.launch(root_id, leaves, approved_plan_tree={"root": {}})
    assert session._handles == {}


def test_duplicate_success_receipts_for_one_generation_fail_closed(env):
    from substrate.event_log import log_event

    log_event(
        "session-1", "cascade.launched",
        payload={"launch_generation": 1, "plan_root_node_id": "root-a"},
        events_dir=env["events"],
    )
    log_event(
        "session-1", "cascade.launched",
        payload={"launch_generation": 1, "plan_root_node_id": "root-b"},
        events_dir=env["events"],
    )
    recovered = reconstruct_session("session-1", events_dir=env["events"])
    assert recovered.researches == []
    assert recovered.plan_root_node_id is None


def test_generation_reservation_is_atomic_across_workers(env):
    from concurrent.futures import ThreadPoolExecutor

    from orchestration.cascade_session import (
        CASCADE_SESSION_TERMINAL,
        LaunchGenerationActive,
        _reserve_launch_generation,
    )
    from substrate.event_log import log_event

    def reserve():
        try:
            return _reserve_launch_generation(
                "session-atomic",
                plan_root_node_id="root",
                events_dir=env["events"],
                requested_generation=None,
            )
        except LaunchGenerationActive:
            return "active"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: reserve(), range(2)))
    assert sorted(outcomes, key=str) == [1, "active"]
    log_event(
        "session-atomic",
        CASCADE_SESSION_TERMINAL,
        payload={"cascade_launch_generation": 1},
        events_dir=env["events"],
    )
    assert reserve() == 2


@pytest.mark.asyncio
async def test_old_parent_completion_cannot_complete_a_relaunch(env, monkeypatch):
    import orchestration.cascade_session as cascade_module
    from substrate.event_log import log_event

    root_id, leaves = _approved_plan(env, subs=["a"])
    loaded = load_tree(root_id, db_path=env["db"])
    first = _make_session(env)
    await first.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    await _drain(first)
    await first.join_and_merge()
    first.record_session_terminal()
    log_event(
        "session-1",
        cascade_module.CASCADE_SYNTHESIS_COMPLETED,
        payload={"cascade_launch_generation": 1},
        events_dir=env["events"],
    )

    second = _make_session(env)
    await second.launch(root_id, leaves, approved_plan_tree=loaded.to_dict())
    await _drain(second)
    monkeypatch.setattr(
        cascade_module, "check_deep_research_complete", lambda _session_id: (True, [])
    )
    assert second.launch_generation == 2
    assert second.is_deep_research_complete() is False
    prior_ids = {
        event["event_id"]
        for event in cascade_module.trajectory("session-1", events_dir=env["events"])
        if isinstance(event.get("event_id"), str)
    }
    with pytest.raises(RuntimeError, match="no current-run parent completion"):
        second.record_synthesis_tail_complete(prior_ids)


def test_leaf_fourth_positional_argument_remains_the_budget():
    from runtime.research_runner import BudgetCap

    budget = BudgetCap(cost_usd=0.75)
    leaf = Leaf("leaf", "question", "question-node", budget)
    assert leaf.budget is budget
    assert leaf.plan_node_local_id is None


@pytest.mark.asyncio
async def test_demo_loop_runner_complete_is_not_deep_research_complete(env):
    """Split-brain guard: runner DONE without synthesis fails P-12/P-13 pair."""
    root_id, leaves = _approved_plan(env, subs=["a"])
    session = _make_session(env)
    await session.launch(root_id, leaves)
    await _drain(session)

    assert session.is_complete()
    assert not session.is_deep_research_complete()
