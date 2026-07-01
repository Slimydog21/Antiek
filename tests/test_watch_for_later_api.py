"""Tests for the Brainstorm watch-for-later API."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    QuestionEscalatedToResearchPayload,
    QuestionIdentifiedPayload,
)


@pytest.fixture
def temp_events(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-watch-later-")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmp, "graph.duckdb"))
    yield {"events_dir": events_dir, "tmpdir": tmp}


def _client(temp_events):
    from interfaces.research.api.app import create_app

    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


def _park_question(
    investigation_id: str,
    question_id: str = "q-1",
    question_text: str = "What should we inspect next?",
    *,
    events_dir: str,
) -> None:
    emit_typed(
        investigation_id,
        QuestionIdentifiedPayload(
            question_id=question_id,
            question_text=question_text,
            anchor_region_id="region-1",
        ),
        document_id="doc-1",
        role="note_taker",
        policy_id="stub/question",
        events_dir=events_dir,
    )


def test_watch_for_later_scans_non_inv_prefixed_trajectories(temp_events):
    _park_question("session-alpha", events_dir=temp_events["events_dir"])
    client = _client(temp_events)

    resp = client.get("/watch-for-later")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["questions"][0]["source_investigation_id"] == "session-alpha"
    assert body["questions"][0]["question_id"] == "q-1"


def test_launch_refuses_already_sharpened_question(temp_events):
    _park_question("session-alpha", events_dir=temp_events["events_dir"])
    emit_typed(
        "session-alpha",
        QuestionEscalatedToResearchPayload(
            question_id="q-1",
            child_investigation_id="inv-existing",
        ),
        document_id="doc-1",
        role="operator",
        policy_id="operator/brainstorm",
        events_dir=temp_events["events_dir"],
    )
    client = _client(temp_events)

    listed = client.get("/watch-for-later").json()
    resp = client.post("/watch-for-later/q-1/launch")

    assert listed["questions"] == []
    assert resp.status_code == 409
    assert trajectory("session-alpha", events_dir=temp_events["events_dir"])


def test_launch_marks_source_question_as_sharpened(temp_events):
    _park_question(
        "session-alpha",
        question_id="q-launch",
        question_text="Should this become an investigation?",
        events_dir=temp_events["events_dir"],
    )
    client = _client(temp_events)

    resp = client.post("/watch-for-later/q-launch/launch")
    listed = client.get("/watch-for-later").json()

    assert resp.status_code == 202
    child_id = resp.json()["investigation_id"]
    source_events = trajectory("session-alpha", events_dir=temp_events["events_dir"])
    child_events = trajectory(child_id, events_dir=temp_events["events_dir"])
    assert listed["questions"] == []
    assert any(
        event["action_type"] == "question.escalated_to_research"
        and event["payload"]["child_investigation_id"] == child_id
        for event in source_events
    )
    assert child_events[0]["action_type"] == "investigation.start_requested"
