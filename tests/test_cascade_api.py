"""DRW SPR-06 transport — the cascade/research REST + SSE surface.

Exercises the wired router via the real ``create_app`` over a tmp DB: the
full operator journey (plan → edit → approve → launch → watch → steer →
cost), the approval gate refusal, durable recovery from the event log, and
an SSE stream smoke. The browse loop is the SPR-02 demo loop, so the journey
is deterministic without a live model or network.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.cascade_routes as cr


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        import hashlib
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture
def client(monkeypatch):
    # Import here so collection of this module does not load all of app.py
    # (ANT-H2V: wrong ::node_id used to hang 30+ min before SIGTERM).
    from interfaces.research.api.app import create_app

    tmpdir = tempfile.mkdtemp(prefix="cascade-api-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    # Hermetic embedding (no sentence-transformers) for plan persistence + funnel.
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    cr._LAUNCHING.clear()
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def _make_approved_plan(client, sub_questions=("sub one", "sub two")):
    r = client.post("/research/plans", json={"problem": "the big problem",
                                             "sub_questions": list(sub_questions)})
    assert r.status_code == 200, r.text
    root = r.json()["root_node_id"]
    client.post(f"/research/plans/{root}/approve", json={"approver": "operator"})
    return root


def _poll_until_terminal(client, session_id, timeout_s=5.0):
    deadline = time.time() + timeout_s
    states = ["pending"]
    while time.time() < deadline:
        r = client.get(f"/research/sessions/{session_id}")
        assert r.status_code == 200, r.text
        states = [x["state"] for x in r.json()["researches"]]
        if all(s in ("done", "stopped", "failed", "budget_halted") for s in states):
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"session {session_id} not terminal in {timeout_s}s; states={states}")


# --------------------------------------------------------------------------
# Plan lifecycle (SPR-05 over HTTP)
# --------------------------------------------------------------------------


def test_budget_defaults_reads_the_contract(client):
    # The entry UI recommends an aggregate stop limit from this value, so it
    # must be the BudgetCap contract default, not a hardcoded API number.
    from runtime.research_runner import BudgetCap
    r = client.get("/research/budget-defaults")
    assert r.status_code == 200, r.text
    body = r.json()
    cap = BudgetCap()
    assert body["per_research_cost_usd"] == cap.cost_usd
    assert body["per_research_max_steps"] == cap.max_steps
    # SPR-05: the monitor reads the real host-local semaphore cap off the
    # contract for its honest "N running, M queued" — not a hardcoded UI number.
    from runtime.research_runner.host_local import DEFAULT_MAX_CONCURRENCY
    assert body["host_local_max_concurrency"] == DEFAULT_MAX_CONCURRENCY


def test_create_plan_returns_editable_tree(client):
    r = client.post("/research/plans", json={"problem": "P", "sub_questions": ["a", "b", "c"]})
    assert r.status_code == 200
    body = r.json()
    assert body["root_node_id"]
    assert len(body["tree"]["root"]["children"]) == 3


def test_get_plan_not_launchable_before_approval(client):
    root = client.post("/research/plans", json={"problem": "P", "sub_questions": ["a"]}).json()["root_node_id"]
    r = client.get(f"/research/plans/{root}")
    assert r.status_code == 200 and r.json()["launchable"] is False


def test_approve_makes_launchable_and_edit_reopens_gate(client):
    root = client.post("/research/plans", json={"problem": "P", "sub_questions": ["a", "b"]}).json()["root_node_id"]
    assert client.post(f"/research/plans/{root}/approve", json={}).json()["launchable"] is True
    # Editing re-opens the gate.
    tree = client.get(f"/research/plans/{root}").json()["tree"]
    child_local = tree["root"]["children"][0]["local_id"]
    r = client.post(f"/research/plans/{root}/edit",
                    json={"op": "reword", "target_local_id": child_local, "question": "reworded"})
    assert r.status_code == 200 and r.json()["launchable"] is False


# --------------------------------------------------------------------------
# Launch gate
# --------------------------------------------------------------------------


def test_launch_refuses_unapproved_plan(client):
    root = client.post("/research/plans", json={"problem": "P", "sub_questions": ["a"]}).json()["root_node_id"]
    r = client.post(f"/research/plans/{root}/launch", json={})
    assert r.status_code == 409
    assert "not approved" in r.json()["detail"]


def test_live_and_recovered_status_preserve_the_approved_plan(client):
    root = _make_approved_plan(client, ("alpha", "beta"))
    launched = client.post(f"/research/plans/{root}/launch", json={})
    assert launched.status_code == 200, launched.text
    sid = launched.json()["session_id"]

    live = client.get(f"/research/sessions/{sid}").json()
    assert live["plan"]["root_node_id"] == root
    assert [n["question"] for n in live["plan"]["tree"]["root"]["children"]] == [
        "alpha", "beta"
    ]
    live_map = {
        r["investigation_id"]: (
            r["question_node_id"], r["plan_node_local_id"], r["control_available"]
        ) for r in live["researches"]
    }
    assert all(qid and local_id and control is True for qid, local_id, control in live_map.values())

    # The session displays its immutable launch receipt, not a later mutable
    # graph-plan read.
    first_local = live["plan"]["tree"]["root"]["children"][0]["local_id"]
    edited = client.post(
        f"/research/plans/{root}/edit",
        json={"op": "reword", "target_local_id": first_local, "question": "changed later"},
    )
    assert edited.status_code == 200, edited.text
    assert client.get(f"/research/sessions/{sid}").json()["plan"] == live["plan"]

    _poll_until_terminal(client, sid)
    cr._SESSIONS.clear()
    recovered = client.get(f"/research/sessions/{sid}")
    assert recovered.status_code == 200, recovered.text
    body = recovered.json()
    assert body["live"] is False
    assert body["plan"] == live["plan"]
    assert {
        r["investigation_id"]: (
            r["question_node_id"], r["plan_node_local_id"], True
        ) for r in body["researches"]
    } == live_map
    assert all(r["control_available"] is False for r in body["researches"])


def test_malformed_launch_snapshot_degrades_to_no_plan(client):
    from substrate.event_log import log_event

    root = _make_approved_plan(client, ("alpha",))
    launched = client.post(f"/research/plans/{root}/launch", json={}).json()
    sid = launched["session_id"]
    _poll_until_terminal(client, sid)
    log_event(
        sid,
        "cascade.launched",
        payload={
            "plan_root_node_id": root,
            "launch_generation": 2,
            "approved_plan_tree": {},
            "researches": [{
                "investigation_id": launched["researches"][0]["investigation_id"],
                "plan_node_local_id": launched["researches"][0]["plan_node_local_id"],
            }],
        },
        role="user_agent",
    )
    cr._SESSIONS.clear()
    body = client.get(f"/research/sessions/{sid}").json()
    assert body["plan"] is None
    assert body["researches"]


@pytest.mark.parametrize("corruption", ["root", "question"])
def test_inconsistent_launch_snapshot_degrades_to_no_plan(client, corruption):
    root = _make_approved_plan(client, ("alpha",))
    launched = client.post(f"/research/plans/{root}/launch", json={}).json()
    sid = launched["session_id"]
    live = client.get(f"/research/sessions/{sid}").json()
    if corruption == "root":
        live["plan"]["root_node_id"] = "unrelated-root"
    else:
        live["researches"][0]["sub_question"] = "different executed question"
    researches = [SimpleNamespace(**research) for research in live["researches"]]
    assert cr._plan_envelope(
        live["plan"]["root_node_id"], live["plan"]["tree"], researches
    ) is None


def test_hostile_launch_snapshot_degrades_to_no_plan():
    snapshot = {
        "root": {},
        "approval": {"state": "approved", "plan_version": float("inf")},
    }
    assert cr._plan_envelope("root", snapshot, []) is None


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_launch_request_rejects_invalid_aggregate_stop_limit(value):
    with pytest.raises(ValueError):
        cr.LaunchRequest(aggregate_budget_usd=value)


def test_launch_request_rejects_non_finite_per_research_limit():
    with pytest.raises(ValueError):
        cr.LaunchRequest(per_research_budget_usd=float("inf"))


# --------------------------------------------------------------------------
# Full launch → watch → cost journey
# --------------------------------------------------------------------------


def test_launch_watch_and_cost(client):
    root = _make_approved_plan(client, ("a", "b", "c"))
    r = client.post(f"/research/plans/{root}/launch", json={"per_research_budget_usd": 1.0})
    assert r.status_code == 200, r.text
    body = r.json()
    sid = body["session_id"]
    assert len(body["researches"]) == 3
    final = _poll_until_terminal(client, sid)
    assert all(x["state"] == "done" for x in final["researches"])
    # Cost meter reflects contract gather stub (3 researches × 2 steps × 0.01).
    cost = client.get(f"/research/sessions/{sid}/cost").json()
    assert cost["session_total_usd"] == pytest.approx(0.06)
    assert cost["session_total_usd"] == pytest.approx(sum(cost["per_research"].values()))


def test_concurrent_launch_of_same_plan_is_rejected(client):
    root = _make_approved_plan(client, ("a",))
    first = client.post(f"/research/plans/{root}/launch", json={})
    assert first.status_code == 200
    sid = first.json()["session_id"]
    # Model the ownership window directly; the guard must reject before any
    # second runner can emit against the same deterministic ids.
    cr._LAUNCHING.add(sid)
    try:
        second = client.post(f"/research/plans/{root}/launch", json={})
    finally:
        cr._LAUNCHING.discard(sid)
    assert second.status_code == 409


# --------------------------------------------------------------------------
# SPR-05 B1 — the cascade fan-out is VISIBLE in the monitor's data source.
#
# MyResearch sources from GET /investigations. Before the fix, that endpoint
# only discovered ``inv-`` files, so a launched cascade's session + leaves
# (``session-…`` / ``…-leaf-N``) NEVER appeared — exactly the "launch N in one
# window" the sprint exists for. This test drives the REAL HTTP launch path
# and asserts the leaves show up in GET /investigations grouped under the
# session (parent_investigation_id == session_id), connecting the launch path
# to the monitor's data source — not hand-built rows.
# --------------------------------------------------------------------------


def test_launched_cascade_appears_in_investigations_grouped_under_session(client):
    root = _make_approved_plan(client, ("alpha", "beta", "gamma"))
    r = client.post(f"/research/plans/{root}/launch", json={"per_research_budget_usd": 1.0})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _poll_until_terminal(client, sid)

    rows = client.get("/investigations", params={"limit": 200}).json()["investigations"]
    by_id = {row["investigation_id"]: row for row in rows}

    # All three leaves are present…
    leaf_ids = [f"{sid}-leaf-{i}" for i in range(3)]
    for lid in leaf_ids:
        assert lid in by_id, f"cascade leaf {lid} missing from the monitor list"
        # …grouped under the session (the link the monitor groups by)…
        assert by_id[lid]["parent_investigation_id"] == sid, by_id[lid]
        # …carrying the leaf's sub-question (so the row is not "Untitled")…
        assert by_id[lid]["question"] in ("alpha", "beta", "gamma"), by_id[lid]
        # …and a real terminal status, not stuck "working".
        assert by_id[lid]["status"] == "completed", by_id[lid]

    # The session parent is itself a row (so the group has a head to nest
    # under), discovered despite carrying no ``inv-`` prefix.
    assert sid in by_id, "cascade session parent missing from the monitor list"


# --------------------------------------------------------------------------
# SPR-05 B2 — a budget-halted research does NOT read as "working" forever.
#
# host_local emits investigation.chase_halted (no terminal completed/failed)
# on a budget halt. The list endpoint must treat that as terminal — matching
# cascade_session.reconstruct_session's BUDGET_HALTED — so the monitor shows
# it as "stopped", never a research that runs forever.
# --------------------------------------------------------------------------


def test_budget_halted_cascade_is_not_working_in_investigations(client):
    # A tiny aggregate cap: the per-research demo loop spends ~0.03 (3×0.01),
    # so a cap below the second research's launch forces a chase-halt that the
    # monitor must surface as terminal, not running.
    root = _make_approved_plan(client, ("a", "b", "c", "d"))
    r = client.post(
        f"/research/plans/{root}/launch",
        json={"per_research_budget_usd": 1.0, "aggregate_budget_usd": 0.04},
    )
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _poll_until_terminal(client, sid)

    rows = client.get("/investigations", params={"limit": 200}).json()["investigations"]
    cascade_rows = [x for x in rows if x["investigation_id"].startswith(sid)]
    assert cascade_rows, "cascade researches missing from the monitor list"

    # Not one cascade research is left reading "working"/running — every one is
    # terminal (completed for those that fit the cap, stopped for the halted).
    assert all(x["status"] != "in_progress" for x in cascade_rows), cascade_rows
    # At least one was budget-halted and surfaces as the honest stopped state
    # (the aggregate cap is small enough to halt a launch).
    assert any(x["status"] == "stopped" for x in cascade_rows), cascade_rows
    # The halted state agrees with the reconstruct path (the honest one).
    from orchestration.cascade_session import reconstruct_session
    rec = reconstruct_session(sid)
    halted = {r.investigation_id for r in rec.researches if r.state == "budget_halted"}
    listed_stopped = {x["investigation_id"] for x in cascade_rows if x["status"] == "stopped"}
    assert halted <= listed_stopped, (halted, listed_stopped)


# --------------------------------------------------------------------------
# SPR-05 MINOR — a stopped research surfaces as "stopped", not "done".
#
# Stop/cancel finishes through investigation.completed with outcome=stopped/
# cancelled. The list endpoint must read the outcome so the spec's "stop one;
# reload" gate shows it honestly, not as a completed research.
# --------------------------------------------------------------------------


def test_stopped_research_surfaces_as_stopped_not_done(client):
    from substrate.event_log import log_event
    from substrate.schemas import ActionType

    # Synthesize the exact event trail host_local writes for a stopped run:
    # start_requested → completed{outcome: stopped}. (The mid-flight stop path
    # itself is covered by test_steer_endpoint_wiring + the runner unit; here we
    # pin that the LIST endpoint reads the outcome, the M1-vocabulary gap.)
    iid = "inv-stopped-001"
    log_event(iid, ActionType.INVESTIGATION_START_REQUESTED,
              payload={"question": "A question the operator stopped"}, role="user_agent")
    log_event(iid, ActionType.INVESTIGATION_COMPLETED,
              payload={"outcome": "stopped"}, role="user_agent")

    rows = client.get("/investigations", params={"limit": 200}).json()["investigations"]
    row = next(x for x in rows if x["investigation_id"] == iid)
    assert row["status"] == "stopped", row
    # And the status filter narrows to it.
    stopped = client.get("/investigations", params={"status": "stopped"}).json()["investigations"]
    assert any(x["investigation_id"] == iid for x in stopped), stopped


# --------------------------------------------------------------------------
# Steer (slow loop so the command lands mid-flight)
# --------------------------------------------------------------------------


def test_steer_endpoint_wiring(client):
    # Endpoint contract: routes the command, safe no-op on a terminal
    # research, 400 on a bad command, 404 on a dead session. The mid-flight
    # steer *isolation* (one research stops, siblings continue) is proven
    # deterministically at the service layer in test_parallel_orchestration —
    # re-testing that timing through a request/response harness that does not
    # run a continuous loop would be flaky, not rigorous.
    root = _make_approved_plan(client, ("a", "b"))
    sid = client.post(f"/research/plans/{root}/launch", json={}).json()["session_id"]
    _poll_until_terminal(client, sid)
    iid = f"{sid}-leaf-0"
    # A command to a finished research is a safe no-op (200), not a crash.
    r = client.post(f"/research/sessions/{sid}/researches/{iid}/steer", json={"kind": "stop"})
    assert r.status_code == 200, r.text
    # Unknown command → 400.
    r = client.post(f"/research/sessions/{sid}/researches/{iid}/steer", json={"kind": "explode"})
    assert r.status_code == 400
    # Dead session → 404.
    r = client.post("/research/sessions/no-such-session/researches/x/steer", json={"kind": "stop"})
    assert r.status_code == 404


# --------------------------------------------------------------------------
# Durable recovery from the event log (session evicted / restart)
# --------------------------------------------------------------------------


def test_session_reconstructs_after_eviction(client):
    root = _make_approved_plan(client, ("a", "b"))
    sid = client.post(f"/research/plans/{root}/launch", json={}).json()["session_id"]
    _poll_until_terminal(client, sid)
    # Simulate a restart: drop the in-memory session.
    cr._SESSIONS.pop(sid, None)
    r = client.get(f"/research/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["live"] is False
    assert {x["investigation_id"] for x in body["researches"]} == {f"{sid}-leaf-0", f"{sid}-leaf-1"}
    assert body["all_terminal"] is True


# --------------------------------------------------------------------------
# SSE stream smoke
# --------------------------------------------------------------------------


def test_session_stream_emits_events(client):
    root = _make_approved_plan(client, ("a",))
    sid = client.post(f"/research/plans/{root}/launch", json={}).json()["session_id"]
    kinds = []
    with client.stream("GET", f"/research/sessions/{sid}/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if not line:
                continue
            text = line if isinstance(line, str) else line.decode()
            if text.startswith("data: "):
                kinds.append(json.loads(text[len("data: "):]).get("kind"))
            if kinds and kinds[-1] == "session_done":
                break
    assert "session_done" in kinds
    assert any(k in ("plan", "step", "note", "status") for k in kinds)


def test_prod_research_loop_factory_uses_contract_gather_stub():
    """ANT-DRL-04: prod factory must not return make_demo_loop."""
    import inspect

    src = inspect.getsource(cr._research_loop_factory)
    assert "make_contract_gather_stub" in src
    assert "make_demo_loop" not in src
    assert callable(cr._research_loop_factory())
