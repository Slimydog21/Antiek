"""The parent-side branch record (specs/antiek-mothership/THREAD-CONTRACT.md §1.3).

Every launch path that starts a child investigation must first write
``investigation.branched`` into the PARENT's trajectory, durably, as the last
step before the child's first event; if that write cannot be made, the child
does not start. The child's ``spawned_from`` keeps pointing back at the branch
through ``parent_event_id``. Before this, a cascade leaf or a chase child named
its parent only in its own log, so losing that log made the dependency
invisible to every reader, the export rights gate included.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from substrate.event_log import (
    BranchNotRecorded,
    log_event,
    record_branch,
    trajectory,
)
from substrate.schemas.events import ActionType

BRANCHED = ActionType.INVESTIGATION_BRANCHED.value
START = ActionType.INVESTIGATION_START_REQUESTED.value
SPAWNED = ActionType.INVESTIGATION_SPAWNED_FROM.value


@pytest.fixture
def events_dir(monkeypatch):
    root = tempfile.mkdtemp(prefix="branch-")
    ev = os.path.join(root, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(root, "graph.duckdb"))
    return ev


def _rows(inv: str, action: str) -> list[dict]:
    return [r for r in trajectory(inv) if r["action_type"] == action]


def _all_starts(events: str) -> int:
    return sum(
        1
        for f in os.listdir(events) if f.endswith(".jsonl")
        for r in trajectory(f[: -len(".jsonl")])
        if r["action_type"] == START
    )


def _assert_branched_first(parent: str, child: str, *, via: str) -> dict:
    """The parent holds the branch, the child's first event comes after it,
    and the child's spawned_from points back at it."""
    branches = [r for r in _rows(parent, BRANCHED)
                if r["payload"]["child_investigation_id"] == child]
    assert len(branches) == 1, trajectory(parent)
    branch = branches[0]
    assert branch["payload"]["via"] == via
    child_rows = trajectory(child)
    assert child_rows, "child never started"
    assert branch["emitted_at"] <= min(r["emitted_at"] for r in child_rows)
    spawned = [r for r in child_rows if r["action_type"] == SPAWNED]
    if spawned:
        assert spawned[0]["payload"]["parent_event_id"] == branch["event_id"]
    return branch


# ── the helper ────────────────────────────────────────────────────────


def test_record_branch_writes_the_edge_into_the_parent(events_dir):
    log_event("inv-p", ActionType.INVESTIGATION_START_REQUESTED, payload={"question": "q"})
    eid = record_branch("inv-p", "inv-c", via="api", spawn_context="why")
    (row,) = _rows("inv-p", BRANCHED)
    assert row["event_id"] == eid
    assert row["payload"]["child_investigation_id"] == "inv-c"
    assert row["payload"]["spawn_context"] == "why"


@pytest.mark.parametrize(("parent", "child"), [("../outside", "inv-c"), ("inv-same", "inv-same"), ("", "inv-c")])
def test_record_branch_refuses_what_it_cannot_record(events_dir, parent, child):
    with pytest.raises(BranchNotRecorded):
        record_branch(parent, child, via="api")


# ── POST /investigations ──────────────────────────────────────────────


def _client() -> TestClient:
    from interfaces.research.api.app import create_app

    return TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))


def test_post_with_parent_records_the_branch_before_the_child(events_dir):
    client = _client()
    assert client.post("/investigations", json={"question": "Root?", "investigation_id": "inv-root"}).status_code == 202
    resp = client.post("/investigations", json={
        "question": "Why?", "parent_investigation_id": "inv-root", "spawn_context": "highlight",
    })
    assert resp.status_code == 202, resp.text
    branch = _assert_branched_first("inv-root", resp.json()["investigation_id"], via="chase")
    assert branch["payload"]["spawn_context"] == "highlight"


def test_post_with_a_parent_that_does_not_exist_is_refused(events_dir):
    resp = _client().post("/investigations", json={
        "question": "Why?", "parent_investigation_id": "inv-nowhere",
    })
    assert resp.status_code == 422 and resp.json()["detail"] == "parent_investigation_not_found"
    assert _all_starts(events_dir) == 0


def test_post_starts_nothing_when_the_branch_cannot_be_recorded(events_dir, monkeypatch):
    import interfaces.research.api.app as app_module

    client = _client()
    client.post("/investigations", json={"question": "Root?", "investigation_id": "inv-root"})

    def refuse(*args, **kwargs):
        raise BranchNotRecorded("simulated unwritable parent log")

    monkeypatch.setattr(app_module, "record_branch", refuse)
    resp = client.post("/investigations", json={"question": "Why?", "parent_investigation_id": "inv-root"})
    assert resp.status_code == 503 and resp.json()["detail"] == "branch_not_recorded"
    assert _all_starts(events_dir) == 1  # only the root's own start


# ── watch-for-later launch ────────────────────────────────────────────


def test_watch_for_later_launch_records_the_branch_in_the_source(events_dir):
    log_event("inv-src", ActionType.QUESTION_IDENTIFIED,
              payload={"question_id": "q-park", "question_text": "What remains open?"})
    resp = _client().post("/watch-for-later/q-park/launch")
    assert resp.status_code == 202, resp.text
    branch = _assert_branched_first("inv-src", resp.json()["investigation_id"], via="watch_for_later")
    assert branch["payload"]["question_id"] == "q-park"


# ── Loop One autonomous chase ─────────────────────────────────────────


class _Bus:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    async def broadcast(self, event) -> None:
        at = getattr(event, "action_type", None)
        self.seen.append((event.investigation_id, str(getattr(at, "value", at))))


def _chase_ctx():
    from orchestration.loop_one.orchestrator import InvestigationContext
    from substrate.schemas import EvidenceRetrieveDeliveredPayload, EvidentiaryGap

    log_event("inv-chase-root", ActionType.INVESTIGATION_START_REQUESTED, payload={"question": "root"})
    ev = EvidenceRetrieveDeliveredPayload(
        sub_question="What is X?", answer="Unknown.", supporting_claims=[],
        evidentiary_gaps=[EvidentiaryGap(gap_description="Quantitative data on X is needed.")],
        insufficient_evidence=True,
    )
    return InvestigationContext(
        investigation_id="inv-chase-root", question="root", evidence=[ev],
        chase_mode="depth", chase_value=3, chase_budget_usd=5.0,
    )


async def test_loop_one_chase_records_the_branch_in_the_parent_first(events_dir):
    from orchestration.loop_one.orchestrator import _maybe_spawn_chase_child

    bus = _Bus()
    await _maybe_spawn_chase_child(_chase_ctx(), bus)
    (branch,) = _rows("inv-chase-root", BRANCHED)
    child = branch["payload"]["child_investigation_id"]
    _assert_branched_first("inv-chase-root", child, via="chase")
    assert bus.seen[0] == ("inv-chase-root", BRANCHED)
    assert (child, START) in bus.seen


async def test_loop_one_chase_halts_when_the_branch_cannot_be_recorded(events_dir, monkeypatch):
    import orchestration.loop_one.orchestrator as orch

    def refuse(*args, **kwargs):
        raise BranchNotRecorded("simulated")

    monkeypatch.setattr(orch, "record_branch", refuse)
    await orch._maybe_spawn_chase_child(_chase_ctx(), _Bus())
    halted = _rows("inv-chase-root", ActionType.INVESTIGATION_CHASE_HALTED.value)
    assert [h["payload"]["reason"] for h in halted] == ["branch_not_recorded"]
    assert _all_starts(events_dir) == 1  # only the root


# ── research runner (cascade leaves) ──────────────────────────────────


async def test_a_leaf_whose_branch_cannot_be_recorded_never_runs(events_dir):
    from runtime.research_runner import (
        BudgetCap,
        BudgetManager,
        HostLocalRunner,
        ResearchPlan,
        RunState,
    )

    calls: list[str] = []

    async def loop(ctx):
        calls.append(ctx.sub_question)
        if False:  # pragma: no cover - an async generator that yields nothing
            yield None

    runner = HostLocalRunner(loop, budget=BudgetManager(), events_dir=events_dir, seal_on_complete=False)
    plan = ResearchPlan(investigation_id="leaf-x", sub_question="sub",
                        parent_investigation_id="../not-a-parent", budget=BudgetCap(cost_usd=1.0))
    handle = await runner.start("leaf-x", plan)
    [ev async for ev in runner.stream(handle)]
    await runner.join()
    assert runner.status(handle).state == RunState.FAILED
    assert calls == []
    failed = _rows("leaf-x", ActionType.INVESTIGATION_FAILED.value)
    assert failed and "branch_not_recorded" in failed[0]["payload"]["error"]


# ── spin-research (a highlighted passage in a book) ───────────────────


def test_spin_research_records_the_branch_in_the_books_reading_thread(monkeypatch):
    from test_acu_meter import isolated_db as _isolated_db  # noqa: F401
    from test_acu_start_charge_before_start import _client as acu_client
    from test_acu_start_charge_before_start import _register_book, _SpyBus

    root = tempfile.mkdtemp(prefix="branch-spin-")
    db = os.path.join(root, "graph.duckdb")
    events = os.path.join(root, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    from substrate.graph import ensure_initialized

    ensure_initialized(db)
    _register_book(db, "doc-spin-branch")
    resp = acu_client(_SpyBus()).post(
        "/books/doc-spin-branch/spin-research",
        json={"page_index": 3, "passage_text": "citrus grafting"},
    )
    assert resp.status_code == 202, resp.text
    branch = _assert_branched_first(
        "read-doc-spin-branch", resp.json()["investigation_id"], via="passage_spin"
    )
    origin = branch["payload"]["origin"]
    assert origin["kind"] == "selection" and origin["document_id"] == "doc-spin-branch"
    assert origin["anchor"]["page_index"] == 3
