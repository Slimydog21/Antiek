"""SPR-09 transport — the suggestions REST surface + daemon-distinction on the
investigation list, wired through the real ``create_app`` over a tmp event log.

Exercises the gates the sprint page names at the HTTP edge:

* M1 — ``GET /research/suggestions`` returns the daemon's scored gaps as
  plain-language threads, read off the event log (not re-derived), with no
  daemon vocabulary in the payload.
* M3 — daemon-spawned researches are distinguished from operator ones on the
  ``GET /investigations`` list via ``spawned_by_daemon`` (the policy_id is
  translated to a boolean, never sent raw).
* M4 — no daemon output → empty suggestions (honest no-result state).
* Surfacing adds no spend — hitting the suggestions endpoint writes no event.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from orchestration.continuous import DAEMON_SPAWN_POLICY_ID


@pytest.fixture
def env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="suggestions-api-test-")
    events = os.path.join(tmpdir, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_HOME", tmpdir)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    # register_providers=False = the honest no-key state.
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return {"client": TestClient(app), "events": events}


def _write(events: str, investigation_id: str, action_type: str, payload: dict,
           *, policy_id: str = "operator-cli") -> None:
    path = os.path.join(events, f"{investigation_id}.jsonl")
    row = {
        "event_id": f"evt-{investigation_id}-{action_type}",
        "investigation_id": investigation_id,
        "action_type": action_type,
        "policy_id": policy_id,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _gap(desc: str, hint: str | None = None) -> dict:
    return {"evidentiary_gaps": [{"gap_description": desc,
                                  "additional_retrieval_suggested": hint}]}


# ── M1: read the daemon's gaps as plain-language suggestions ───────────


def test_suggestions_returns_plain_threads_from_the_event_log(env):
    ev = env["events"]
    _write(ev, "inv-A", "evidence.retrieve.delivered", _gap("What is the dispatch threshold?", "check §14.4"))
    _write(ev, "inv-B", "evidence.retrieve.delivered", _gap("What is the dispatch threshold?"))
    r = env["client"].get("/research/suggestions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    s = body["suggestions"][0]
    assert s["question"] == "What is the dispatch threshold?"
    assert s["seen_in_research_count"] == 2
    assert s["suggested_retrieval"] == "check §14.4"
    assert s["source_investigation_id"] in ("inv-A", "inv-B")
    # No daemon vocabulary leaks into the payload.
    raw = r.text.lower()
    assert "evidentiary_gap" not in raw
    assert "chase score" not in raw
    assert "policy_id" not in raw


def test_suggestions_empty_is_honest(env):
    # No gap events → empty list, never canned threads (M4 no-daemon state).
    r = env["client"].get("/research/suggestions")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "suggestions": []}


def test_suggestions_endpoint_is_read_only(env):
    """Hitting the endpoint writes no event — surfacing adds no spend."""
    ev = env["events"]
    _write(ev, "inv-A", "evidence.retrieve.delivered", _gap("a gap to surface"))
    _write(ev, "inv-B", "evidence.retrieve.delivered", _gap("a gap to surface"))
    before = {f: os.path.getsize(os.path.join(ev, f)) for f in os.listdir(ev)}
    env["client"].get("/research/suggestions")
    after = {f: os.path.getsize(os.path.join(ev, f)) for f in os.listdir(ev)}
    assert before == after


def test_suggestions_respects_display_limit(env):
    ev = env["events"]
    for i in range(6):
        # Each gap cross-pollinated so it scores > 0.
        _write(ev, f"inv-{i}", "evidence.retrieve.delivered", _gap(f"distinct gap number {i}"))
        _write(ev, f"inv-x{i}", "evidence.retrieve.delivered", _gap(f"distinct gap number {i}"))
    r = env["client"].get("/research/suggestions?limit=2")
    assert r.status_code == 200
    assert r.json()["count"] == 2


# ── M3: daemon-spawned researches distinguished on the list ────────────


def test_investigation_list_flags_daemon_spawned(env):
    ev = env["events"]
    # An operator-launched research.
    _write(ev, "inv-op", "investigation.start_requested",
           {"question": "operator question"}, policy_id="operator-cli")
    # A daemon-spawned chase (carries the daemon's spawn policy_id).
    _write(ev, "inv-daemon", "investigation.start_requested",
           {"question": "loop-found question"}, policy_id=DAEMON_SPAWN_POLICY_ID)

    r = env["client"].get("/investigations")
    assert r.status_code == 200, r.text
    by_id = {s["investigation_id"]: s for s in r.json()["investigations"]}
    assert by_id["inv-op"]["spawned_by_daemon"] is False
    assert by_id["inv-daemon"]["spawned_by_daemon"] is True
    # The raw policy_id is never sent to the client — only the boolean.
    assert "policy_id" not in r.text
