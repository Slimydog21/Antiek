"""Speak SPR-10 M4 — the compounding interviewer carries cross-session
context, with the consent-scope privacy filter intact.

ACCEPTANCE: a 2nd interview in the same project sees prior-session
context (the project gets sharper as it aggregates); a RECORD-only
source never surfaces in another interview.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.speak import consent as consent_mod
from substrate.speak import project
from substrate.speak.consent import ConsentScope
from substrate.speak.interviewer_context import build_conditioning_context
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-compound-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="compound_test")


def _interview(con, project_id, iid, *, scopes):
    con.execute(
        "INSERT INTO interviews (interview_id, project_id, status) VALUES (?, ?, 'completed')",
        [iid, project_id],
    )
    consent_mod.record_consent(con, interview_id=iid, scopes=scopes, project_id=project_id)


def test_second_interview_sees_first_session_context(db):
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="private_never_published")
        # Session 1 — interviewee A (attribute-consented so it may inform others).
        _interview(con, p.project_id, "iv-a", scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE])
        record_claim(con, project_id=p.project_id, interview_id="iv-a",
                     text="He ran the village bakery for thirty years.", confidence=0.8)
        # Session 2 — interviewee B is invited later; the interviewer should
        # carry A's contribution into B's conditioning context.
        _interview(con, p.project_id, "iv-b", scopes=[ConsentScope.RECORD])
        ctx = build_conditioning_context(con, project_id=p.project_id, for_interview_id="iv-b")
        assert any("bakery" in s for s in ctx.accumulated_insights), \
            "the 2nd interview must see the 1st session's accumulated context"


def test_record_only_source_never_surfaces_in_another_interview(db):
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="private_never_published")
        # A consented to RECORD only — their words must not inform anyone else.
        _interview(con, p.project_id, "iv-a", scopes=[ConsentScope.RECORD])
        record_claim(con, project_id=p.project_id, interview_id="iv-a",
                     text="A private detail A only agreed to record.", confidence=0.8)
        _interview(con, p.project_id, "iv-b", scopes=[ConsentScope.RECORD])
        ctx = build_conditioning_context(con, project_id=p.project_id, for_interview_id="iv-b")
        assert all("private detail" not in s for s in ctx.accumulated_insights)
        assert ctx.withheld_for_privacy >= 1  # the filter did work
