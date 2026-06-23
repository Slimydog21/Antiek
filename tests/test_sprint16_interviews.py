"""Tests for Sprint 16 interview machinery: graph ops + role + API.

Sprint 16 partial-take: substrate-side machinery only. Voice/WebRTC
(Sprint 17) + standalone interview.antiek.ai deploy stay deferred.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from roles.interviewer import (
    INTERVIEWER_SYSTEM_PROMPT,
    InterviewerContext,
    InterviewerValidationError,
    TranscriptTurn,
    parse_interviewer_response,
    render_full_prompt,
    render_user_template,
)


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-sprint16i-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


def _client(temp_substrate):
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────
# 1. Graph ops
# ─────────────────────────────────────────────────────────────────────


def test_insert_interview_project_returns_id(temp_substrate):
    from runtime.db_lock import connect_write
    from substrate.graph import insert_interview_project
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test") as con:
        pid = insert_interview_project(
            con, title="A biographical project",
            topic_description="Long-form bio interviews",
        )
    assert pid.startswith("ivp-")


def test_append_interview_turn_promotes_status_on_first(temp_substrate):
    import duckdb

    from runtime.db_lock import connect_write
    from substrate.graph import (
        append_interview_turn,
        insert_interview,
        insert_interview_project,
    )
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test") as con:
        pid = insert_interview_project(con, title="P")
        iid = insert_interview(con, project_id=pid, informant_handle="alice")
        count = append_interview_turn(
            con, interview_id=iid, role="interviewer", text="Hello.",
        )
    assert count == 1
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (status, started,) = con.execute(
            "SELECT status, started_at FROM interviews WHERE interview_id = ?",
            [iid],
        ).fetchone()
    finally:
        con.close()
    assert status == "in_progress"
    assert started is not None


def test_append_interview_turn_unknown_id_raises(temp_substrate):
    from runtime.db_lock import connect_write
    from substrate.graph import append_interview_turn
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test") as con:
        with pytest.raises(ValueError, match="not found"):
            append_interview_turn(
                con, interview_id="intv-nope",
                role="interviewer", text="x",
            )


def test_append_interview_turn_invalid_role_raises(temp_substrate):
    from runtime.db_lock import connect_write
    from substrate.graph import (
        append_interview_turn,
        insert_interview,
        insert_interview_project,
    )
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test") as con:
        pid = insert_interview_project(con, title="P")
        iid = insert_interview(con, project_id=pid)
        with pytest.raises(ValueError, match="unknown turn role"):
            append_interview_turn(
                con, interview_id=iid, role="moderator", text="x",
            )


# ─────────────────────────────────────────────────────────────────────
# 2. Interviewer role
# ─────────────────────────────────────────────────────────────────────


def test_render_user_template_first_turn_shows_no_transcript():
    ctx = InterviewerContext(
        project_title="P",
        topic_description="Biography of operator's career.",
        framing="Looking for stories, not facts.",
        must_cover=["What got you started?", "What changed in 2020?"],
    )
    out = render_user_template(ctx)
    assert "P" in out
    assert "Biography of operator" in out
    assert "0. What got you started?" in out
    assert "first interviewer utterance" in out


def test_render_user_template_consent_branch():
    ctx = InterviewerContext(
        project_title="P", topic_description="x", framing="x",
        consent_recorded=False,
    )
    out = render_user_template(ctx)
    assert "Consent NOT YET recorded" in out


def test_render_user_template_renders_transcript():
    ctx = InterviewerContext(
        project_title="P", topic_description="x", framing="x",
        consent_recorded=True,
        transcript=[
            TranscriptTurn(role="interviewer", text="What got you started?"),
            TranscriptTurn(role="informant", text="A long story."),
        ],
    )
    out = render_user_template(ctx)
    assert "**interviewer:**" in out
    assert "What got you started?" in out
    assert "**informant:**" in out


def test_render_full_prompt_returns_system_and_user():
    sys_p, user_p = render_full_prompt(
        InterviewerContext(project_title="P", topic_description="x", framing="x"),
    )
    assert sys_p == INTERVIEWER_SYSTEM_PROMPT


def test_system_prompt_voice_discipline_lockin():
    # Hard discipline lock-in: forbidden hedging modifiers must be
    # named (operator's standing rule about LLM tells).
    sp = INTERVIEWER_SYSTEM_PROMPT.lower()
    assert "perhaps" in sp
    assert "hedging" in sp


def test_parser_happy_path():
    raw = (
        '{"interviewer_text": "Tell me what you were doing in 2020.", '
        '"should_end": false, '
        '"must_cover_remaining_indices": [1, 2], '
        '"follow_up_for_prior_turn": false, '
        '"reasoning_note": "covered q0 implicitly."}'
    )
    r = parse_interviewer_response(raw)
    assert r.should_end is False
    assert r.must_cover_remaining_indices == [1, 2]
    assert "Tell me" in r.interviewer_text


def test_parser_end_signal():
    raw = (
        '{"interviewer_text": "Thank you. We covered everything.", '
        '"should_end": true, "must_cover_remaining_indices": [], '
        '"follow_up_for_prior_turn": false}'
    )
    r = parse_interviewer_response(raw)
    assert r.should_end is True


def test_parser_rejects_short_utterance():
    raw = '{"interviewer_text": "?", "should_end": false, "must_cover_remaining_indices": []}'
    with pytest.raises(InterviewerValidationError, match="chars"):
        parse_interviewer_response(raw)


def test_parser_rejects_non_int_indices():
    raw = (
        '{"interviewer_text": "Next question?", "should_end": false, '
        '"must_cover_remaining_indices": ["a", 1]}'
    )
    with pytest.raises(InterviewerValidationError, match="non-negative ints"):
        parse_interviewer_response(raw)


def test_parser_no_json_rejected():
    with pytest.raises(InterviewerValidationError, match="no JSON"):
        parse_interviewer_response("not json")


# ─────────────────────────────────────────────────────────────────────
# 3. API endpoints
# ─────────────────────────────────────────────────────────────────────


def test_post_project_returns_summary(temp_substrate):
    client = _client(temp_substrate)
    r = client.post("/interview-projects", json={
        "title": "Operator bio",
        "topic_description": "30-year career retrospective",
        "must_cover": ["start", "pivot", "now"],
        "framing": "Loose. Stories over facts.",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Operator bio"
    assert body["must_cover"] == ["start", "pivot", "now"]
    assert body["interview_count"] == 0


def test_list_projects(temp_substrate):
    client = _client(temp_substrate)
    for t in ("Pa", "Pb", "Pc"):
        assert client.post("/interview-projects", json={"title": t}).status_code == 201
    body = client.get("/interview-projects").json()
    assert len(body) == 3


def test_invite_interview_404_for_unknown_project(temp_substrate):
    client = _client(temp_substrate)
    r = client.post("/interviews", json={
        "project_id": "ivp-nope",
        "informant_handle": "alice",
    })
    assert r.status_code == 404


def test_invite_and_post_turn_flow(temp_substrate):
    client = _client(temp_substrate)
    p = client.post("/interview-projects", json={
        "title": "P", "must_cover": ["q1"],
    }).json()
    inv = client.post("/interviews", json={
        "project_id": p["project_id"], "informant_handle": "alice",
    }).json()
    assert inv["status"] == "invited"

    detail = client.get(f"/interviews/{inv['interview_id']}").json()
    assert detail["project_title"] == "P"
    assert detail["transcript"] == []
    assert detail["status"] == "invited"

    r = client.post(
        f"/interviews/{inv['interview_id']}/turn",
        json={"role": "interviewer", "text": "First question?"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "in_progress"
    assert body["turn_count"] == 1


def test_complete_interview_marks_status(temp_substrate):
    client = _client(temp_substrate)
    p = client.post("/interview-projects", json={"title": "P"}).json()
    inv = client.post("/interviews", json={"project_id": p["project_id"]}).json()
    client.post(
        f"/interviews/{inv['interview_id']}/turn",
        json={"role": "interviewer", "text": "x?"},
    )
    r = client.post(
        f"/interviews/{inv['interview_id']}/complete",
        json={},
    )
    assert r.status_code == 202
    assert r.json()["status"] == "completed"


def test_complete_unknown_interview_404(temp_substrate):
    client = _client(temp_substrate)
    r = client.post("/interviews/intv-nope/complete", json={})
    assert r.status_code == 404


def test_get_interview_404(temp_substrate):
    client = _client(temp_substrate)
    r = client.get("/interviews/intv-nope")
    assert r.status_code == 404


def test_turn_invalid_role_422(temp_substrate):
    client = _client(temp_substrate)
    p = client.post("/interview-projects", json={"title": "P"}).json()
    inv = client.post("/interviews", json={"project_id": p["project_id"]}).json()
    r = client.post(
        f"/interviews/{inv['interview_id']}/turn",
        json={"role": "moderator", "text": "x"},
    )
    assert r.status_code == 422
