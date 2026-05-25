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

from interfaces.research.api.app import create_app
import interfaces.research.api.cascade_routes as cr
from runtime.research_runner import make_demo_loop


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        import hashlib
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="cascade-api-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    # Hermetic embedding (no sentence-transformers) for plan persistence + funnel.
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
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
    # Cost meter reflects the runner's numbers (3 researches × 3 steps × 0.01).
    cost = client.get(f"/research/sessions/{sid}/cost").json()
    assert cost["session_total_usd"] == pytest.approx(0.09)
    assert cost["session_total_usd"] == pytest.approx(sum(cost["per_research"].values()))


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
