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
    monkeypatch.setenv("ANTIEK_ALLOW_LOCAL_HARD_CEILING", "1")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    # Hermetic embedding (no sentence-transformers) for plan persistence + funnel.
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    cr._HARD_CEILING_RUNS.clear()
    cr._HARD_CEILING_LAUNCHING.clear()
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


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_launch_request_rejects_invalid_aggregate_stop_limit(value):
    with pytest.raises(ValueError):
        cr.LaunchRequest(aggregate_budget_usd=value)


def test_launch_request_rejects_non_finite_per_research_limit():
    with pytest.raises(ValueError):
        cr.LaunchRequest(per_research_budget_usd=float("inf"))


def test_hard_ceiling_auto_decomposition_fails_before_paid_dispatch(client):
    r = client.post(
        "/research/plans",
        json={"problem": "P", "spend_mode": "hard_ceiling"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "hard_ceiling_provider_ineligible"


def test_hard_launch_rejects_plan_automatically_decomposed_in_stop_limit_mode(
    client, monkeypatch
):
    class Fixed:
        def decompose(self, question, *, context=""):
            return [cr.SubQuestion("a")]

    monkeypatch.setattr(
        cr,
        "_decompose",
        lambda problem, max_depth: cr.build_plan(
            problem, decomposer=Fixed(), max_depth=max_depth
        ),
    )
    created = client.post("/research/plans", json={"problem": "P"})
    assert created.status_code == 200, created.text
    root = created.json()["root_node_id"]
    client.post(f"/research/plans/{root}/approve", json={})

    launched = client.post(
        f"/research/plans/{root}/launch",
        json={"spend_mode": "hard_ceiling", "hard_ceiling_usd": "1.00"},
    )

    assert launched.status_code == 409
    assert launched.json()["detail"]["code"] == "hard_ceiling_plan_ineligible"


def test_hard_launch_rejects_ceiling_above_ledger_maximum(client):
    root = _make_approved_plan(client, ("a",))
    launched = client.post(
        f"/research/plans/{root}/launch",
        json={
            "spend_mode": "hard_ceiling",
            "hard_ceiling_usd": "46116860184273879.04",
        },
    )
    assert launched.status_code == 422


def test_hard_launch_rejects_decimal_exponent_overflow(client):
    root = _make_approved_plan(client, ("a",))
    launched = client.post(
        f"/research/plans/{root}/launch",
        json={"spend_mode": "hard_ceiling", "hard_ceiling_usd": "1e999999"},
    )
    assert launched.status_code == 422


def test_launch_rejects_caller_authored_owner_identity(client):
    root = _make_approved_plan(client, ("a",))
    r = client.post(
        f"/research/plans/{root}/launch",
        json={
            "spend_mode": "hard_ceiling",
            "hard_ceiling_usd": "1.00",
            "owner_id": "spoofed-owner",
        },
    )
    assert r.status_code == 422


def test_hard_launch_requires_explicit_local_authority(client, monkeypatch):
    root = _make_approved_plan(client, ("a",))
    monkeypatch.delenv("ANTIEK_ALLOW_LOCAL_HARD_CEILING")
    r = client.post(
        f"/research/plans/{root}/launch",
        json={"spend_mode": "hard_ceiling", "hard_ceiling_usd": "1.00"},
    )
    assert r.status_code == 403


def test_hard_ceiling_launch_binds_plan_and_receipts_zero_cost_work(
    client, monkeypatch
):
    root = _make_approved_plan(client, ("a", "b"))
    r = client.post(
        f"/research/plans/{root}/launch",
        json={
            "spend_mode": "hard_ceiling",
            "hard_ceiling_usd": "2.00",
            "per_research_budget_usd": 1.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["spend_mode"] == "hard_ceiling"
    assert body["hard_ceiling"]["ceiling_cents"] == 200
    assert body["hard_ceiling"]["blocked_stages"] == [
        "synthesizer",
        "knowledge_extractor",
    ]
    assert len(body["hard_ceiling"]["plan_digest"]) == 64
    sid = body["session_id"]
    _poll_until_terminal(client, sid)

    gateway, binding = cr._HARD_CEILING_RUNS[cr._SESSIONS[sid]]
    balance = gateway.ledger.balance(binding.run_id)
    assert balance.status.value == "closed_reconciled"
    assert balance.authorized_spent_cents == 0
    events = gateway.ledger.events(binding.run_id)
    assert [event.event_kind for event in events].count("zero_prepared") == 4
    assert [event.event_kind for event in events].count("zero_completed") == 4


def test_hard_ceiling_authority_changes_with_plan_revision_and_ceiling(
    client, monkeypatch
):
    monkeypatch.setattr(cr, "_SYNTHESIS_TAIL_RUNNER", None)
    root = _make_approved_plan(client, ("a",))
    first = cr._hard_ceiling_binding(
        root_id=root,
        session_id=f"session-{root}",
        owner_id="owner-1",
        tree=cr.load_tree(root, db_path=cr._db()),
        request=cr.LaunchRequest(
            spend_mode="hard_ceiling", hard_ceiling_usd="1.00"
        ),
    )
    tree = client.get(f"/research/plans/{root}").json()["tree"]
    local_id = tree["root"]["children"][0]["local_id"]
    assert client.post(
        f"/research/plans/{root}/edit",
        json={"op": "reword", "target_local_id": local_id, "question": "changed"},
    ).json()["launchable"] is False
    client.post(f"/research/plans/{root}/approve", json={})
    changed_tree = cr.load_tree(root, db_path=cr._db())
    assert changed_tree is not None
    revised = cr._hard_ceiling_binding(
        root_id=root,
        session_id=f"session-{root}",
        owner_id="owner-1",
        tree=changed_tree,
        request=cr.LaunchRequest(
            spend_mode="hard_ceiling", hard_ceiling_usd="1.00"
        ),
    )
    higher_ceiling = cr._hard_ceiling_binding(
        root_id=root,
        session_id=f"session-{root}",
        owner_id="owner-1",
        tree=changed_tree,
        request=cr.LaunchRequest(
            spend_mode="hard_ceiling", hard_ceiling_usd="2.00"
        ),
    )
    assert revised.approval_revision == first.approval_revision + 1
    assert len({first.run_id, revised.run_id, higher_ceiling.run_id}) == 3
    assert len({first.plan_digest, revised.plan_digest, higher_ceiling.plan_digest}) == 3


def test_hard_ceiling_refuses_exa_before_loop_construction(client, monkeypatch):
    root = _make_approved_plan(client, ("a",))
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "exa")
    monkeypatch.setattr(cr, "_SYNTHESIS_TAIL_RUNNER", None)
    monkeypatch.setattr(
        cr,
        "_research_loop_factory",
        lambda: (_ for _ in ()).throw(AssertionError("loop must not be constructed")),
    )
    r = client.post(
        f"/research/plans/{root}/launch",
        json={"spend_mode": "hard_ceiling", "hard_ceiling_usd": "1.00"},
    )
    assert r.status_code == 409
    assert "Exa" in r.json()["detail"]["message"]


def test_hard_ceiling_skips_configured_paid_tail_without_affecting_launch(
    client, monkeypatch
):
    calls = 0

    async def paid_tail(*args):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(cr, "_SYNTHESIS_TAIL_RUNNER", paid_tail)
    root = _make_approved_plan(client, ("a",))
    r = client.post(
        f"/research/plans/{root}/launch",
        json={"spend_mode": "hard_ceiling", "hard_ceiling_usd": "1.00"},
    )
    assert r.status_code == 200, r.text
    _poll_until_terminal(client, r.json()["session_id"])
    assert calls == 0


def test_identical_hard_launch_retry_returns_existing_session_without_rerun(
    client, monkeypatch
):
    monkeypatch.setattr(cr, "_SYNTHESIS_TAIL_RUNNER", None)
    root = _make_approved_plan(client, ("a",))
    payload = {
        "spend_mode": "hard_ceiling",
        "hard_ceiling_usd": "1.00",
        "per_research_budget_usd": 1.0,
    }
    first = client.post(f"/research/plans/{root}/launch", json=payload)
    assert first.status_code == 200, first.text
    sid = first.json()["session_id"]
    _poll_until_terminal(client, sid)
    session_before = cr._SESSIONS[sid]
    gateway, binding = cr._HARD_CEILING_RUNS[session_before]
    events_before = gateway.ledger.events(binding.run_id)

    replay = client.post(f"/research/plans/{root}/launch", json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["session_id"] == sid
    assert cr._SESSIONS[sid] is session_before
    assert gateway.ledger.events(binding.run_id) == events_before


def test_hard_launch_replay_after_restart_uses_durable_run_without_rerun(
    client, monkeypatch
):
    root = _make_approved_plan(client, ("a",))
    payload = {"spend_mode": "hard_ceiling", "hard_ceiling_usd": "1.00"}
    first = client.post(f"/research/plans/{root}/launch", json=payload)
    assert first.status_code == 200, first.text
    sid = first.json()["session_id"]
    _poll_until_terminal(client, sid)
    gateway, binding = cr._HARD_CEILING_RUNS[cr._SESSIONS[sid]]
    events_before = gateway.ledger.events(binding.run_id)

    cr._SESSIONS.clear()
    cr._HARD_CEILING_RUNS.clear()
    monkeypatch.setattr(
        cr,
        "_research_loop_factory",
        lambda: (_ for _ in ()).throw(AssertionError("replay must not build a loop")),
    )
    replay = client.post(f"/research/plans/{root}/launch", json=payload)

    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["session_id"] == sid
    assert sid not in cr._SESSIONS
    assert gateway.ledger.events(binding.run_id) == events_before


def test_interrupted_hard_launch_is_not_reported_as_a_durable_replay(
    client, monkeypatch
):
    root = _make_approved_plan(client, ("a",))
    payload = {"spend_mode": "hard_ceiling", "hard_ceiling_usd": "1.00"}
    monkeypatch.setattr(
        cr,
        "_embedding_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("setup failed")),
    )
    with pytest.raises(RuntimeError, match="setup failed"):
        client.post(f"/research/plans/{root}/launch", json=payload)

    replay = client.post(f"/research/plans/{root}/launch", json=payload)
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "hard_ceiling_launch_interrupted"


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
