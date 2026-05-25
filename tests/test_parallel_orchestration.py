"""DRW SPR-06 — parallel launch + glass-box session orchestration.

Mechanical gates: launch enforces the SPR-05 approval gate; the multiplexed
stream carries all researches; steer routes to one research; aggregate cost
reconciles; merge-on-complete links findings to sub-questions; the session
reconstructs from the event log alone (durability); one research failing is
isolated.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile

import pytest

from orchestration.cascade_session import CascadeSession, Leaf, reconstruct_session
from runtime.research_runner import (
    BudgetCap, Command, CommandKind, HostLocalRunner, PromotionFunnel, RunState,
    make_demo_loop,
)
from runtime.research_runner.host_local import LoopContext
from roles.cascade_planner import (
    PlanNotApproved, approve_plan, build_plan, persist_tree, SubQuestion,
)
from roles.cascade_planner.persist import load_tree
from substrate.graph.schema import init_database_at_path
from runtime.db_lock import connect_read
from processing.embedding import set_default_embedding_provider, _reset_default_provider


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class _Dec:
    def __init__(self, subs):
        self._subs = subs

    def decompose(self, q, *, context=""):
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
    tree = build_plan("the problem", decomposer=_Dec(subs)).tree
    root_id = persist_tree(tree, investigation_id="session-1",
                           embedding_provider=_FakeEmbedding(), db_path=env["db"])
    approve_plan(root_id, approver="operator", investigation_id="session-1", db_path=env["db"])
    loaded = load_tree(root_id, db_path=env["db"])
    leaves = [Leaf(investigation_id=f"leaf-{i}", sub_question=c.question,
                   question_node_id=c.graph_node_id)
              for i, c in enumerate(loaded.root.children)]
    return root_id, leaves


def _make_session(env, loop_fn=None, **runner_kw):
    funnel = PromotionFunnel(db_path=env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        loop_fn or make_demo_loop(steps=2, emit_note=True),
        events_dir=env["events"], seal_on_complete=False, on_emit=funnel.submit, **runner_kw,
    )
    return CascadeSession("session-1", runner=runner, funnel=funnel,
                          events_dir=env["events"], db_path=env["db"]), runner, funnel


async def _drain(session):
    return [ev async for ev in session.stream()]


# --------------------------------------------------------------------------
# M1 — launch + approval enforcement
# --------------------------------------------------------------------------


async def test_launch_refuses_unapproved_plan(env):
    tree = build_plan("p", decomposer=_Dec(["a"])).tree
    root_id = persist_tree(tree, investigation_id="session-1",
                           embedding_provider=_FakeEmbedding(), db_path=env["db"])
    session, _, _ = _make_session(env)
    with pytest.raises(PlanNotApproved):
        await session.launch(root_id, [Leaf("leaf-0", "a")])


async def test_launch_approved_plan_starts_one_investigation_per_leaf(env):
    root_id, leaves = _approved_plan(env, subs=["a", "b", "c"])
    session, runner, funnel = _make_session(env)
    handles = await session.launch(root_id, leaves)
    assert len(handles) == 3
    await _drain(session)
    await session.join_and_merge()
    states = {s.investigation_id: s.state for s in session.status()}
    assert all(st == RunState.DONE.value for st in states.values())


# --------------------------------------------------------------------------
# M2 — multiplexed stream
# --------------------------------------------------------------------------


async def test_stream_multiplexes_all_researches(env):
    root_id, leaves = _approved_plan(env, subs=["a", "b"])
    session, _, funnel = _make_session(env)
    await session.launch(root_id, leaves)
    events = await _drain(session)
    await session.join_and_merge()
    iids = {ev.investigation_id for ev in events}
    assert {"leaf-0", "leaf-1"} <= iids                 # both researches in one stream
    assert any(ev.kind == "done" for ev in events)


# --------------------------------------------------------------------------
# M3 — steer routing
# --------------------------------------------------------------------------


async def test_steer_routes_to_one_research(env):
    root_id, leaves = _approved_plan(env, subs=["a", "b"])
    session, runner, funnel = _make_session(env, loop_fn=make_demo_loop(steps=8, delay_s=0.02))
    await session.launch(root_id, leaves)
    await asyncio.sleep(0.01)
    await session.steer("leaf-0", Command(CommandKind.STOP))
    await _drain(session)
    await session.join_and_merge()
    states = {s.investigation_id: s.state for s in session.status()}
    assert states["leaf-0"] == RunState.STOPPED.value
    assert states["leaf-1"] == RunState.DONE.value      # sibling unaffected
    # steer to an unknown research is a safe no-op
    await session.steer("nonexistent", Command(CommandKind.PAUSE))


# --------------------------------------------------------------------------
# M4 — aggregate cost
# --------------------------------------------------------------------------


async def test_aggregate_cost_reconciles(env):
    root_id, leaves = _approved_plan(env, subs=["a", "b"])
    session, _, funnel = _make_session(
        env, loop_fn=make_demo_loop(steps=2, cost_per_step=0.01, emit_note=False))
    await session.launch(root_id, leaves)
    await _drain(session)
    await session.join_and_merge()
    cost = session.aggregate_cost()
    # 2 researches * 2 steps * 0.01 = 0.04
    assert cost["session_total_usd"] == pytest.approx(0.04)
    assert cost["session_total_usd"] == pytest.approx(sum(cost["per_research"].values()))


# --------------------------------------------------------------------------
# M5 — merge-on-complete
# --------------------------------------------------------------------------


async def test_merge_links_findings_to_subquestion(env):
    root_id, leaves = _approved_plan(env, subs=["a", "b"])
    session, _, funnel = _make_session(env)   # demo loop emits 1 note each
    await session.launch(root_id, leaves)
    await _drain(session)
    result = await session.join_and_merge()
    assert result["linked_findings"] >= 2     # each leaf's insight linked to its sub-question
    con = connect_read(env["db"])
    try:
        # The sub-question node has a resolved_by edge to a promoted insight.
        for leaf in leaves:
            n = con.execute(
                "SELECT count(*) FROM edges WHERE source_node_id=? AND relation='resolved_by'",
                [leaf.question_node_id],
            ).fetchone()[0]
            assert n >= 1
    finally:
        con.close()


# --------------------------------------------------------------------------
# M6 — durability: reconstruct from the event log alone
# --------------------------------------------------------------------------


async def test_session_reconstructs_from_event_log(env):
    root_id, leaves = _approved_plan(env, subs=["a", "b", "c"])
    session, _, funnel = _make_session(env)
    await session.launch(root_id, leaves)
    await _drain(session)
    await session.join_and_merge()
    # Throw away all in-memory session state; rebuild from the JSONL only.
    recovery = reconstruct_session("session-1", events_dir=env["events"])
    assert {r.investigation_id for r in recovery.researches} == {"leaf-0", "leaf-1", "leaf-2"}
    assert recovery.all_terminal
    assert all(r.state == RunState.DONE.value for r in recovery.researches)


# --------------------------------------------------------------------------
# M7 — failure isolation
# --------------------------------------------------------------------------


async def test_one_failure_isolated(env):
    root_id, leaves = _approved_plan(env, subs=["a", "b"])

    async def dispatch_loop(ctx: LoopContext):
        fail = ctx.investigation_id == "leaf-0"
        async for ev in make_demo_loop(steps=3, fail_on_step=1 if fail else None)(ctx):
            yield ev

    session, _, funnel = _make_session(env, loop_fn=dispatch_loop)
    await session.launch(root_id, leaves)
    events = await _drain(session)
    await session.join_and_merge()
    states = {s.investigation_id: s.state for s in session.status()}
    assert states["leaf-0"] == RunState.FAILED.value
    assert states["leaf-1"] == RunState.DONE.value       # sibling continues
    # the error is visible in the stream, not swallowed
    assert any(ev.kind == "error" and ev.investigation_id == "leaf-0" for ev in events)
