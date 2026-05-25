"""SPR-02 M5 — remote-exec cost flow + budget enforcement, FAKE provider only.

Gates:

  * remote-exec cost emits ``DispatchCall`` events indistinguishable in shape
    from host-local dispatch (the SPR-07 cost surface sees them with no
    special-casing — only the ``provider`` field names "fake-daytona");
  * the cost charged equals the cost reported by the sandbox (realized, not an
    estimate presented as actual) — the ledger reconciles with the dispatch
    stream by construction;
  * per-research and aggregate ``TOTAL_ACQUISITION_BUDGET_USD`` are enforced;
    exceeding the aggregate halts *new* launches and surfaces why.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.remote_exec import (
    RemoteResearchRunner,
    RemoteStepEvent,
    record_remote_dispatch,
)
from runtime.research_runner import (
    BudgetCap,
    BudgetExceeded,
    BudgetManager,
    ResearchPlan,
    RunState,
)
from substrate.event_log import trajectory
from substrate.schemas.events import ActionType
from tests.remote_exec_fakes import FakeProvider


@pytest.fixture
def events_dir(monkeypatch):
    d = tempfile.mkdtemp()
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_EVENTS_DIR", ev)
    return ev


def _plan(i: int, *, cap=1.0, max_steps=50) -> ResearchPlan:
    return ResearchPlan(investigation_id=f"inv-{i}", sub_question=f"q{i}?",
                        budget=BudgetCap(cost_usd=cap, max_steps=max_steps))


def test_dispatch_call_emitted_in_host_local_shape(events_dir):
    # record one remote dispatch and read the event back — it validates as a
    # DispatchCall and carries the canonical fields.
    budget = BudgetManager()
    budget.register("inv-0", 1.0)
    ev = RemoteStepEvent(seq=1, kind="step", text="s", cost_usd=0.02, tokens=11,
                         provider="fake-daytona", model="leaf",
                         data={"input_tokens": 5, "output_tokens": 11,
                               "latency_ms": 30, "tier": "pro"})
    eid = record_remote_dispatch(investigation_id="inv-0", event=ev, budget=budget,
                                 events_dir=events_dir)
    assert eid
    rows = trajectory("inv-0", events_dir=events_dir)
    dispatch_rows = [r for r in rows if r["action_type"] == ActionType.DISPATCH_CALL.value]
    assert len(dispatch_rows) == 1
    payload = dispatch_rows[0]["payload"]
    # Indistinguishable shape: the same fields a host-local dispatch carries.
    assert payload["provider"] == "fake-daytona"
    assert payload["cost_usd"] == pytest.approx(0.02)
    assert payload["input_tokens"] == 5
    assert payload["output_tokens"] == 11
    assert payload["tier"] == "pro"
    # the charge equals the reported cost — realized, not estimated
    assert budget.spent("inv-0") == pytest.approx(0.02)


async def test_per_step_cost_emits_dispatch_calls_and_reconciles(events_dir):
    prov = FakeProvider(steps=3, cost_per_step=0.01)
    r = RemoteResearchRunner(prov, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    _ = [ev async for ev in r.stream(h)]
    rows = trajectory("inv-0", events_dir=events_dir)
    dispatch_rows = [x for x in rows if x["action_type"] == ActionType.DISPATCH_CALL.value]
    assert len(dispatch_rows) == 3                       # one per cost-bearing step
    total = sum(x["payload"]["cost_usd"] for x in dispatch_rows)
    # ledger reconciles with the dispatch stream by construction
    assert r.cost(h).spent_usd == pytest.approx(total)
    assert r.cost(h).spent_usd == pytest.approx(0.03)


async def test_per_research_cap_halts_one_leaf(events_dir):
    # Tiny cap, expensive steps — the leaf halts at BUDGET_HALTED, not its
    # siblings.
    prov = FakeProvider(steps=20, cost_per_step=0.10)
    r = RemoteResearchRunner(prov, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0, cap=0.25))
    _ = [ev async for ev in r.stream(h)]
    assert r.status(h).state == RunState.BUDGET_HALTED
    rows = trajectory("inv-0", events_dir=events_dir)
    halted = [x for x in rows if x["action_type"] == ActionType.INVESTIGATION_CHASE_HALTED.value]
    assert halted, "expected a chase_halted event recording the per-research cap"
    assert halted[-1]["payload"]["reason"] == "per_research"
    assert "inv-0" in prov.torn_down


async def test_aggregate_cap_halts_new_launches(events_dir):
    # Aggregate cap of $0.30. First two leaves spend it; the third is refused
    # at launch with a surfaced reason — new launches stop, not the running
    # ones.
    budget = BudgetManager(aggregate_cap_usd=0.30)
    prov = FakeProvider(steps=3, cost_per_step=0.05, emit_note=False)
    r = RemoteResearchRunner(prov, budget=budget, events_dir=events_dir,
                             seal_on_complete=False)
    # run two leaves to completion (each spends 3 * 0.05 = 0.15 → 0.30 total)
    for i in (0, 1):
        h = await r.start(f"inv-{i}", _plan(i, cap=1.0))
        _ = [ev async for ev in r.stream(h)]
    assert budget.aggregate_spent == pytest.approx(0.30)
    assert not budget.can_launch(0.0)
    # third launch is refused with a surfaced reason
    h2 = await r.start("inv-2", _plan(2, cap=1.0))
    events = [ev async for ev in r.stream(h2)]
    assert r.status(h2).state == RunState.BUDGET_HALTED
    statuses = [e for e in events if e.kind == "status"]
    assert any("aggregate acquisition budget" in s.text for s in statuses)
    rows = trajectory("inv-2", events_dir=events_dir)
    halted = [x for x in rows if x["action_type"] == ActionType.INVESTIGATION_CHASE_HALTED.value]
    assert halted and halted[-1]["payload"]["reason"] == "aggregate_budget"


async def test_aggregate_cap_default_is_total_acquisition_budget(events_dir):
    # When no explicit aggregate cap, the budget defaults to
    # TOTAL_ACQUISITION_BUDGET_USD — the shared aggregate per the master spec
    # open question (remote-exec shares the aggregate budget).
    from substrate.constants import TOTAL_ACQUISITION_BUDGET_USD
    budget = BudgetManager()
    assert budget.aggregate_cap_usd == pytest.approx(float(TOTAL_ACQUISITION_BUDGET_USD))


def test_budget_exceeded_propagates_from_record_remote_dispatch():
    # The cost path raises BudgetExceeded when a charge breaks the aggregate
    # cap — the runner's halt arm depends on this propagation.
    budget = BudgetManager(aggregate_cap_usd=0.05)
    budget.register("inv-0", 1.0)
    ev = RemoteStepEvent(seq=1, kind="step", cost_usd=0.10, tokens=1,
                         provider="fake", model="leaf", data={"tier": "pro"})
    with pytest.raises(BudgetExceeded) as exc:
        record_remote_dispatch(investigation_id="inv-0", event=ev, budget=budget)
    assert exc.value.scope == "aggregate"
