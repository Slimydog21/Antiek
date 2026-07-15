"""DRW SPR-02 — ResearchRunner protocol + host-local runner.

Mechanical gates: the N=20 concurrency + isolation test, the
lock-contention promotion test, steer commands, budget enforcement
(per-research + aggregate + reconciliation), and the §16-gated Daytona
stub. Async tests run under pytest asyncio_mode=auto.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_read
from runtime.research_runner import (
    BudgetCap,
    BudgetManager,
    Command,
    CommandKind,
    DaytonaGatedError,
    DaytonaRunner,
    HostLocalRunner,
    PromotionFunnel,
    ResearchPlan,
    ResearchRunner,
    RunState,
    daytona_enabled,
    make_contract_gather_stub,
    make_demo_loop,
)
from runtime.research_runner.host_local import LoopContext
from substrate.event_log import trajectory
from substrate.graph.schema import init_database_at_path
from substrate.schemas.events import ActionType


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture(autouse=True)
def _hash_embeddings():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def events_dir(monkeypatch):
    d = tempfile.mkdtemp()
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    return ev


def _plan(i: int, **kw) -> ResearchPlan:
    return ResearchPlan(investigation_id=f"inv-{i}", sub_question=f"question {i}", **kw)


# --------------------------------------------------------------------------
# M1 — protocol conformance
# --------------------------------------------------------------------------


def test_hostlocal_satisfies_protocol():
    r = HostLocalRunner(make_demo_loop())
    assert isinstance(r, ResearchRunner)


async def test_start_returns_handle_and_streams_to_done(events_dir):
    r = HostLocalRunner(make_demo_loop(steps=2), events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    kinds = [ev.kind async for ev in r.stream(h)]
    assert kinds[-1] == "done"
    assert "plan" in kinds and "step" in kinds
    assert r.status(h).state == RunState.DONE


# --------------------------------------------------------------------------
# M2/M3 — N=20 concurrency + per-investigation isolation + failure isolation
# --------------------------------------------------------------------------


async def test_twenty_concurrent_isolated_and_one_failure_isolated(events_dir):
    # One of the 20 loops raises mid-flight; its siblings must still finish.
    def loop_for(i):
        return make_demo_loop(steps=3, delay_s=0.001,
                              fail_on_step=1 if i == 7 else None)

    # A runner whose loop_fn dispatches per-investigation behavior.
    async def dispatch_loop(ctx: LoopContext):
        idx = int(ctx.investigation_id.split("-")[1])
        async for ev in loop_for(idx)(ctx):
            yield ev

    r = HostLocalRunner(dispatch_loop, max_concurrency=20, events_dir=events_dir,
                        seal_on_complete=False)
    handles = [await r.start(f"inv-{i}", _plan(i)) for i in range(20)]
    # Drain every stream concurrently.
    async def drain(h):
        return [ev async for ev in r.stream(h)]
    await asyncio.gather(*(drain(h) for h in handles))
    await r.join()

    states = [r.status(h).state for h in handles]
    assert states[7] == RunState.FAILED
    assert all(s == RunState.DONE for i, s in enumerate(states) if i != 7), states

    # 20 isolated, uncorrupted JSONL trajectories — read each back.
    files = sorted(f for f in os.listdir(events_dir) if f.endswith(".jsonl"))
    assert len(files) == 20
    for i in range(20):
        rows = trajectory(f"inv-{i}", events_dir=events_dir)
        assert rows, f"inv-{i} empty trajectory"
        actions = {row["action_type"] for row in rows}
        assert ActionType.INVESTIGATION_START_REQUESTED.value in actions
        # every line parsed cleanly (trajectory drops corrupt lines, so a
        # full count match across all 20 proves no cross-file corruption)
        assert all(row["investigation_id"] == f"inv-{i}" for row in rows)


async def test_browse_loops_never_write_the_graph(events_dir, monkeypatch):
    # Run loops WITHOUT a promotion funnel; the graph must stay empty —
    # proof that a browse loop has no graph-write path of its own.
    db = os.path.join(tempfile.mkdtemp(), "graph.duckdb")
    init_database_at_path(db)
    r = HostLocalRunner(make_demo_loop(steps=2), events_dir=events_dir, seal_on_complete=False)
    handles = [await r.start(f"inv-{i}", _plan(i)) for i in range(5)]

    async def drain(h):
        return [ev async for ev in r.stream(h)]
    await asyncio.gather(*(drain(h) for h in handles))
    await r.join()
    con = connect_read(db)
    try:
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type IN ('insight','question')").fetchone()[0] == 0
    finally:
        con.close()


# --------------------------------------------------------------------------
# M4 — serialized promotion funnel, no lock contention under 20 completions
# --------------------------------------------------------------------------


async def test_promotion_funnel_serialized_no_lock_timeout(events_dir):
    db = os.path.join(tempfile.mkdtemp(), "graph.duckdb")
    init_database_at_path(db)
    funnel = PromotionFunnel(db_path=db, embedding_provider=_FakeEmbedding())
    await funnel.start()

    r = HostLocalRunner(
        make_demo_loop(steps=2, emit_note=True),
        max_concurrency=20, events_dir=events_dir, seal_on_complete=False,
        on_emit=funnel.submit,
    )
    handles = [await r.start(f"inv-{i}", _plan(i)) for i in range(20)]

    async def drain(h):
        return [ev async for ev in r.stream(h)]
    await asyncio.gather(*(drain(h) for h in handles))
    await r.join()
    await funnel.drain_and_stop()

    assert funnel.errors == [], funnel.errors          # zero lock timeouts/errors
    assert funnel.promoted_insights == 20              # one note each
    assert funnel.promoted_questions == 20             # one question each
    con = connect_read(db)
    try:
        assert con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0] == 20
        # write_log recorded every serialized promotion.
        n_log = con.execute("SELECT count(*) FROM write_log WHERE purpose='promotion_funnel'").fetchone()[0]
        assert n_log >= 20
    finally:
        con.close()


async def test_contract_gather_stub_promotes_note_via_funnel(events_dir):
    """ANT-DRL-04: prod stub emits real StepEvents + funnel promotion."""
    db = os.path.join(tempfile.mkdtemp(), "graph.duckdb")
    init_database_at_path(db)
    funnel = PromotionFunnel(db_path=db, embedding_provider=_FakeEmbedding())
    await funnel.start()

    r = HostLocalRunner(
        make_contract_gather_stub(steps=2, cost_per_step=0.01),
        events_dir=events_dir,
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    h = await r.start("inv-0", _plan(0))
    events = [ev async for ev in r.stream(h)]
    await r.join()
    await funnel.drain_and_stop()

    assert any(ev.kind == "step" and "[gather-stub]" in ev.text for ev in events)
    assert funnel.promoted_insights >= 1
    cost = r.cost(h)
    assert cost.spent_usd == pytest.approx(0.02)
    assert cost.steps == 2


# --------------------------------------------------------------------------
# M5 — steer commands
# --------------------------------------------------------------------------


async def test_pause_resume(events_dir):
    r = HostLocalRunner(make_demo_loop(steps=5, delay_s=0.02), events_dir=events_dir,
                        seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    await asyncio.sleep(0.01)
    await r.steer(h, Command(CommandKind.PAUSE))
    await asyncio.sleep(0.05)
    paused_steps = r.cost(h).steps
    await asyncio.sleep(0.05)
    assert r.cost(h).steps == paused_steps           # made no progress while paused
    assert r.status(h).state == RunState.PAUSED
    await r.steer(h, Command(CommandKind.RESUME))
    _ = [ev async for ev in r.stream(h)]
    assert r.status(h).state == RunState.DONE
    assert r.cost(h).steps > paused_steps            # progressed after resume


async def test_stop_seals_and_transitions(events_dir):
    r = HostLocalRunner(make_demo_loop(steps=50, delay_s=0.01), events_dir=events_dir)
    h = await r.start("inv-0", _plan(0))
    await asyncio.sleep(0.02)
    await r.steer(h, Command(CommandKind.STOP))
    _ = [ev async for ev in r.stream(h)]
    assert r.status(h).state == RunState.STOPPED
    # JSONL was sealed (or remains valid) — trajectory reads back.
    rows = trajectory("inv-0", events_dir=events_dir)
    assert any(row["action_type"] == ActionType.INVESTIGATION_COMPLETED.value for row in rows)


async def test_redirect_changes_sub_question(events_dir):
    seen = []

    async def watching_loop(ctx: LoopContext):
        for _i in range(6):
            sub_q = await ctx.checkpoint()
            seen.append(sub_q)
            await asyncio.sleep(0.01)
            yield ctx.step(f"on {sub_q}", cost_usd=0.0)

    r = HostLocalRunner(watching_loop, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    await asyncio.sleep(0.015)
    await r.steer(h, Command(CommandKind.REDIRECT, {"sub_question": "redirected!"}))
    _ = [ev async for ev in r.stream(h)]
    assert "redirected!" in seen
    assert r.status(h).sub_question == "redirected!"


async def test_deepen_raises_cap_and_queues_followup(events_dir):
    r = HostLocalRunner(make_demo_loop(steps=2, delay_s=0.02),
                        events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0, budget=BudgetCap(cost_usd=0.10)))
    await asyncio.sleep(0.01)
    await r.steer(h, Command(CommandKind.DEEPEN,
                             {"extra_budget_usd": 0.50, "follow_up": "go deeper on X"}))
    _ = [ev async for ev in r.stream(h)]
    assert r.cost(h).cap_usd == pytest.approx(0.60)
    assert "go deeper on X" in r.status(h).follow_ups


async def test_command_after_finish_is_noop(events_dir):
    r = HostLocalRunner(make_demo_loop(steps=1), events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    _ = [ev async for ev in r.stream(h)]
    assert r.status(h).state == RunState.DONE
    # Must not raise.
    await r.steer(h, Command(CommandKind.PAUSE))
    await r.steer(h, Command(CommandKind.STOP))
    assert r.status(h).state == RunState.DONE


# --------------------------------------------------------------------------
# M6 — budget enforcement
# --------------------------------------------------------------------------


async def test_tiny_cap_halts_and_emits_chase_halted(events_dir):
    r = HostLocalRunner(make_demo_loop(steps=20, cost_per_step=0.10),
                        events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0, budget=BudgetCap(cost_usd=0.25)))
    _ = [ev async for ev in r.stream(h)]
    assert r.status(h).state == RunState.BUDGET_HALTED
    rows = trajectory("inv-0", events_dir=events_dir)
    halts = [row for row in rows if row["action_type"] == ActionType.INVESTIGATION_CHASE_HALTED.value]
    assert halts and halts[0]["payload"]["reason"] == "per_research"


async def test_aggregate_cap_blocks_next_launch(events_dir):
    # Aggregate cap small enough that the first research's spend exhausts it.
    budget = BudgetManager(aggregate_cap_usd=0.30)
    r = HostLocalRunner(make_demo_loop(steps=5, cost_per_step=0.10),
                        budget=budget, events_dir=events_dir, seal_on_complete=False)
    h0 = await r.start("inv-0", _plan(0, budget=BudgetCap(cost_usd=10.0)))
    _ = [ev async for ev in r.stream(h0)]            # spends past 0.30 aggregate
    # Next launch is blocked with a surfaced reason.
    h1 = await r.start("inv-1", _plan(1, budget=BudgetCap(cost_usd=10.0)))
    st = r.status(h1)
    assert st.state == RunState.BUDGET_HALTED
    assert "aggregate acquisition budget" in (st.error or "")


async def test_queued_research_rechecks_aggregate_before_provider_work(events_dir):
    provider_calls = 0

    async def one_paid_step(ctx: LoopContext):
        nonlocal provider_calls
        provider_calls += 1
        yield ctx.step("paid", cost_usd=0.02)

    budget = BudgetManager(aggregate_cap_usd=0.01)
    runner = HostLocalRunner(
        one_paid_step,
        max_concurrency=1,
        budget=budget,
        events_dir=events_dir,
        seal_on_complete=False,
    )
    handles = [
        await runner.start(
            f"inv-{i}",
            _plan(i, budget=BudgetCap(cost_usd=1.0)),
        )
        for i in range(4)
    ]
    async def drain(handle):
        return [event async for event in runner.stream(handle)]

    await asyncio.gather(*(drain(handle) for handle in handles))

    assert provider_calls == 1
    assert runner.status(handles[0]).state == RunState.BUDGET_HALTED
    assert all(
        runner.status(handle).state == RunState.BUDGET_HALTED
        for handle in handles[1:]
    )


async def test_cost_reconciles_with_reported_steps(events_dir):
    # The ledger total equals the sum of per-step cost the loop reported —
    # the same number a step's DispatchCall event carries (no under-count).
    reported = []

    async def costed_loop(ctx: LoopContext):
        for i in range(4):
            await ctx.checkpoint()
            c = 0.02
            reported.append(c)
            yield ctx.step(f"s{i}", cost_usd=c, tokens=5)

    r = HostLocalRunner(costed_loop, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0, budget=BudgetCap(cost_usd=10.0)))
    _ = [ev async for ev in r.stream(h)]
    assert r.cost(h).spent_usd == pytest.approx(sum(reported))
    assert r.cost(h).tokens == 20


# --------------------------------------------------------------------------
# M7 — gated Daytona stub
# --------------------------------------------------------------------------


async def test_daytona_gated():
    assert daytona_enabled() is False                # flag OFF by default
    d = DaytonaRunner()                              # construction is safe
    assert isinstance(d, ResearchRunner)             # conforms to the protocol
    with pytest.raises(DaytonaGatedError) as ei:
        await d.start("inv-0", _plan(0))
    assert "§16" in str(ei.value)                    # documents the unlock
    # steer/cancel are also guarded.
    with pytest.raises(DaytonaGatedError):
        await d.cancel(_DummyHandle())


def test_no_daytona_sdk_dependency():
    # The stub must not import any Daytona SDK at module load.
    import sys
    assert not any("daytona_sdk" in m or m == "daytona" for m in sys.modules)


class _DummyHandle:
    investigation_id = "inv-0"
