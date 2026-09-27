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
    """The parent holds the branch, the child's first launched event comes
    after it, and the child's spawned_from points back at it. A reserved
    child's reservation predates every launch by design, so it is not one."""
    branches = [r for r in _rows(parent, BRANCHED)
                if r["payload"]["child_investigation_id"] == child]
    assert len(branches) == 1, trajectory(parent)
    branch = branches[0]
    assert branch["payload"]["via"] == via
    child_rows = [r for r in trajectory(child)
                  if r["action_type"] != ActionType.INVESTIGATION_RESERVED.value]
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


# ── money: lineage is settled before anything is charged ──────────────


def _acu_env(monkeypatch, *, limit: int, used: int):
    """An isolated graph + events dir with the hard ACU gate at ``limit``."""
    from test_acu_start_charge_before_start import _seed

    root = tempfile.mkdtemp(prefix="branch-acu-")
    db = os.path.join(root, "graph.duckdb")
    events = os.path.join(root, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    from substrate.graph import ensure_initialized

    ensure_initialized(db)
    _seed(db, limit=limit, used=used)
    return db, events


def _charged_ids(db: str) -> list[str]:
    from test_acu_start_charge_before_start import _ledger

    return _ledger(db)[0]


def test_refusals_before_the_branch_charge_nothing(monkeypatch):
    # Codex round 7: the parent refusal ran after the ACU charge, so a 422
    # left a charge for an investigation that never started.
    import interfaces.research.api.app as app_module

    db, events = _acu_env(monkeypatch, limit=10, used=0)
    client = _client()
    root = client.post("/investigations", json={"question": "Root?", "investigation_id": "inv-acu-root"})
    assert root.status_code == 202, root.text
    missing = client.post("/investigations", json={"question": "Why?", "parent_investigation_id": "inv-missing"})
    assert missing.status_code == 422
    assert _charged_ids(db) == ["inv-acu-root"]

    def refuse(*args, **kwargs):
        raise BranchNotRecorded("simulated")

    monkeypatch.setattr(app_module, "record_branch", refuse)
    unwritable = client.post("/investigations", json={"question": "Why?", "parent_investigation_id": "inv-acu-root"})
    assert unwritable.status_code == 503 and unwritable.json()["detail"] == "branch_not_recorded"
    assert _charged_ids(db) == ["inv-acu-root"]


def test_a_capacity_refusal_after_the_branch_abandons_it(monkeypatch):
    # The branch is written before the charge; a refused charge comes before
    # any start event, so the same request abandons exactly that branch. The
    # refusal is the atomic commit's: a twin is charged between the precheck
    # (which passes) and the commit, exhausting the cap.
    from test_acu_start_charge_before_start import _OWNER

    import interfaces.research.api.compute_capacity_gate as G
    from runtime.db_lock import connect_write
    from substrate.compute_capacity.acu_meter import record_investigation_start_acu

    db, events = _acu_env(monkeypatch, limit=2, used=0)
    client = _client()
    assert client.post("/investigations", json={"question": "Root?", "investigation_id": "inv-cap-root"}).status_code == 202
    real_precheck = G.run_capacity_precheck

    def precheck_then_twin(request, **kwargs):
        gate = real_precheck(request, **kwargs)
        with connect_write(db, purpose="test:twin") as con:
            record_investigation_start_acu(con, owner_user_id=_OWNER, investigation_id="inv-twin")
        return gate

    monkeypatch.setattr(G, "run_capacity_precheck", precheck_then_twin)
    resp = client.post("/investigations", json={
        "question": "Why?", "parent_investigation_id": "inv-cap-root", "investigation_id": "inv-cap-child",
    })
    assert resp.status_code == 429, resp.text
    (branch,) = _rows("inv-cap-root", BRANCHED)
    (abandon,) = _rows("inv-cap-root", ActionType.INVESTIGATION_BRANCH_ABANDONED.value)
    assert abandon["payload"]["branch_event_id"] == branch["event_id"]
    assert abandon["payload"]["child_investigation_id"] == "inv-cap-child"
    assert trajectory("inv-cap-child") == []
    assert _charged_ids(db) == ["inv-cap-root", "inv-twin"]


# ── reserved ids: every entrypoint takes the reserving parent ─────────


def test_an_identical_retry_of_a_reserved_launch_replays_it(monkeypatch):
    # Codex round 8: once the child had started, the retry resolved no
    # reserving parent, so its start payload differed from the stored one and
    # an identical request answered 409. A reservation binds the id for good,
    # so both an implicit and an explicit retry replay the first launch: the
    # same start event, no second branch, no second charge.
    from substrate.event_log import record_reservation

    db, events = _acu_env(monkeypatch, limit=10, used=0)
    client = _client()
    assert client.post("/investigations", json={"question": "Root?", "investigation_id": "inv-rr-root"}).status_code == 202
    record_reservation("inv-rr-child", "inv-rr-root", question_id="q-rr")
    body = {"question": "Chase it", "investigation_id": "inv-rr-child"}
    first = client.post("/investigations", json=body)
    retry = client.post("/investigations", json=body)
    explicit = client.post("/investigations", json={**body, "parent_investigation_id": "inv-rr-root"})
    assert [r.status_code for r in (first, retry, explicit)] == [202, 202, 202], (retry.text, explicit.text)
    assert first.json()["start_event_id"] == retry.json()["start_event_id"] == explicit.json()["start_event_id"]
    assert len(_rows("inv-rr-child", START)) == 1
    _assert_branched_first("inv-rr-root", "inv-rr-child", via="reserved_launch")
    assert sorted(_charged_ids(db)) == ["inv-rr-child", "inv-rr-root"]


def _runner(kind: str, events: str):
    """A research runner of ``kind`` and a list that records whether it ran."""
    from runtime.research_runner import BudgetManager, HostLocalRunner

    ran: list[str] = []
    if kind == "remote":
        from runtime.remote_exec import RemoteResearchRunner
        from tests.remote_exec_fakes import FakeProvider

        prov = FakeProvider(steps=1)
        return RemoteResearchRunner(prov, events_dir=events, seal_on_complete=False), prov.provisioned

    async def loop(ctx):
        ran.append(ctx.sub_question)
        if False:  # pragma: no cover - an async generator that yields nothing
            yield None

    return HostLocalRunner(loop, budget=BudgetManager(), events_dir=events, seal_on_complete=False), ran


async def _run_leaf(runner, investigation_id: str, plan):
    handle = await runner.start(investigation_id, plan)
    [ev async for ev in runner.stream(handle)]
    if hasattr(runner, "join"):
        await runner.join()
    return runner.status(handle).state


@pytest.mark.parametrize("kind", ["host_local", "remote"])
async def test_a_runner_launch_into_a_reserved_id_branches_from_the_reserving_parent(events_dir, kind):
    # Codex round 8: both runners launched a reserved id whose plan named no
    # parent with no branch anywhere. They now resolve the parent the same
    # way the API does and branch from the reservation's parent.
    from runtime.research_runner import BudgetCap, ResearchPlan, RunState
    from substrate.event_log import record_reservation

    log_event("inv-rn-root", START, payload={"question": "q"})
    record_reservation("leaf-rn", "inv-rn-root", question_id="q-rn")
    runner, ran = _runner(kind, events_dir)
    plan = ResearchPlan(investigation_id="leaf-rn", sub_question="sub", budget=BudgetCap(cost_usd=1.0))
    assert await _run_leaf(runner, "leaf-rn", plan) != RunState.FAILED
    assert ran, "the reserved leaf never ran"
    _assert_branched_first("inv-rn-root", "leaf-rn", via="reserved_launch")
    (spawned,) = _rows("leaf-rn", SPAWNED)
    assert spawned["payload"]["parent_investigation_id"] == "inv-rn-root"


@pytest.mark.parametrize("kind", ["host_local", "remote"])
async def test_a_runner_launch_into_a_reserved_id_under_another_parent_never_runs(events_dir, kind):
    # The launch is not this id's to make: nothing runs, no parent gains a
    # branch, and the reserved log keeps only its reservation, so the
    # reserving parent can still launch it.
    from runtime.research_runner import BudgetCap, ResearchPlan, RunState
    from substrate.event_log import record_reservation

    for parent in ("inv-rm-root", "inv-rm-other"):
        log_event(parent, START, payload={"question": "q"})
    record_reservation("leaf-rm", "inv-rm-root", question_id="q-rm")
    runner, ran = _runner(kind, events_dir)
    plan = ResearchPlan(investigation_id="leaf-rm", sub_question="sub",
                        parent_investigation_id="inv-rm-other", budget=BudgetCap(cost_usd=1.0))
    assert await _run_leaf(runner, "leaf-rm", plan) == RunState.FAILED
    assert ran == []
    assert _rows("inv-rm-root", BRANCHED) == _rows("inv-rm-other", BRANCHED) == []
    assert [r["action_type"] for r in trajectory("leaf-rm")] == [ActionType.INVESTIGATION_RESERVED.value]


@pytest.mark.parametrize("kind", ["host_local", "remote"])
async def test_a_runner_refuses_a_plan_for_another_investigation(events_dir, kind):
    # The branch names the id the runner was started with; a plan for another
    # id would run into that other log with no branch of its own.
    from runtime.research_runner import BudgetCap, ResearchPlan, RunState

    log_event("inv-pm-root", START, payload={"question": "q"})
    runner, ran = _runner(kind, events_dir)
    plan = ResearchPlan(investigation_id="leaf-pm-other", sub_question="sub",
                        parent_investigation_id="inv-pm-root", budget=BudgetCap(cost_usd=1.0))
    assert await _run_leaf(runner, "leaf-pm", plan) == RunState.FAILED
    assert ran == []
    assert _rows("inv-pm-root", BRANCHED) == []
    assert trajectory("leaf-pm") == trajectory("leaf-pm-other") == []

