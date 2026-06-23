"""Speak SPR-04 — compounding interviewer tests.

Rigor #3: the first interviewee (no accumulated context), a huge project
(budget/rank), a leading question (corroboration prompts ask openly),
and — the mandatory gate — the consent-scope privacy rule: conditioning
B on A's statements must never leak A's record-only statements. Plus the
no-training gate (capture works; harvest refused until G8).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.loop_3.unlock_gate import Loop3UnlockRequired
from substrate.speak import async_interview as ai
from substrate.speak import corroboration, interviewer_capture, invitations, project
from substrate.speak.consent import ConsentScope, record_consent
from substrate.speak.interviewer_context import build_conditioning_context
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


class StubEmbedding:
    dimension = 4

    def encode(self, text):
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-interviewer-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="interviewer_test")


def _invitee(con, project_id, email, *, scopes):
    iv = invitations.invite_stakeholder(con, project_id=project_id, informant_email=email)
    record_consent(con, interview_id=iv.interview_id, scopes=scopes)
    return iv.interview_id


# ── M1 accumulated-context conditioning ─────────────────────────────────


def test_later_interviewee_conditioned_on_earlier(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        a = _invitee(con, p.project_id, "a@x.com", scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE])
        b = _invitee(con, p.project_id, "b@x.com", scopes=[ConsentScope.RECORD])
        record_claim(con, project_id=p.project_id, interview_id=a,
                     text="He ran the village bakery for thirty years.",
                     about_subject=True, subject_ref="the-dad")
        ctx = build_conditioning_context(con, project_id=p.project_id, for_interview_id=b)
        assert any("bakery" in s for s in ctx.accumulated_insights)


def test_first_interviewee_has_no_accumulated_insights(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        a = _invitee(con, p.project_id, "a@x.com", scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE])
        # No other interviewees' claims yet.
        ctx = build_conditioning_context(con, project_id=p.project_id, for_interview_id=a)
        assert ctx.accumulated_insights == []


def test_context_is_budgeted(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        a = _invitee(con, p.project_id, "a@x.com", scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE])
        b = _invitee(con, p.project_id, "b@x.com", scopes=[ConsentScope.RECORD])
        for i in range(40):
            record_claim(con, project_id=p.project_id, interview_id=a,
                         text=f"Distinct fact number {i} about him.",
                         about_subject=True, subject_ref="the-dad")
        ctx = build_conditioning_context(con, project_id=p.project_id, for_interview_id=b, max_items=12)
        assert len(ctx.accumulated_insights) <= 12


# ── M2 open-question chasing ────────────────────────────────────────────


def test_open_questions_become_prompts(db):
    guide = {"must_cover": [{"id": "q1", "text": "What was his proudest moment?"}]}
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography", interview_guide=guide)
        b = _invitee(con, p.project_id, "b@x.com", scopes=[ConsentScope.RECORD])
        ctx = build_conditioning_context(con, project_id=p.project_id, for_interview_id=b)
        assert any("proudest moment" in g.text for g in ctx.open_questions)


# ── M3 corroboration probing — without leading ──────────────────────────


def test_single_sourced_claim_generates_open_corroboration_prompt(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        a = _invitee(con, p.project_id, "a@x.com", scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE])
        b = _invitee(con, p.project_id, "b@x.com", scopes=[ConsentScope.RECORD])
        record_claim(con, project_id=p.project_id, interview_id=a,
                     text="He saved a stranger from drowning in 1968.",
                     about_subject=True, subject_ref="the-dad")
        corroboration.corroborate_project(con, p.project_id)  # single-sourced
        ctx = build_conditioning_context(con, project_id=p.project_id, for_interview_id=b)
        assert len(ctx.corroboration_targets) == 1
        prompt = ctx.corroboration_targets[0].text
        # Non-leading: the prompt must NOT restate the claim's assertion.
        assert "saved a stranger from drowning" not in prompt


# ── M4 deepening ────────────────────────────────────────────────────────


def test_under_explored_subject_generates_deepening_prompt(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        a = _invitee(con, p.project_id, "a@x.com", scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE])
        b = _invitee(con, p.project_id, "b@x.com", scopes=[ConsentScope.RECORD])
        record_claim(con, project_id=p.project_id, interview_id=a,
                     text="His brother emigrated separately.",
                     about_subject=False, subject_ref="the-brother")
        ctx = build_conditioning_context(con, project_id=p.project_id, for_interview_id=b)
        assert any("the-brother" in g.text for g in ctx.deepening_targets)


# ── consent-scope privacy rule (MANDATORY) ──────────────────────────────


def test_record_only_source_never_leaks_into_other_interview(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        # A consents to RECORD only — not attribute.
        a = _invitee(con, p.project_id, "a@x.com", scopes=[ConsentScope.RECORD])
        b = _invitee(con, p.project_id, "b@x.com", scopes=[ConsentScope.RECORD])
        record_claim(con, project_id=p.project_id, interview_id=a,
                     text="A SECRET detail A shared only on the record.",
                     about_subject=True, subject_ref="the-dad")
        corroboration.corroborate_project(con, p.project_id)
        ctx = build_conditioning_context(con, project_id=p.project_id, for_interview_id=b)
        # A's record-only statement must NOT surface in B's context — not
        # as an insight, not as a corroboration probe.
        assert all("SECRET" not in s for s in ctx.accumulated_insights)
        assert ctx.corroboration_targets == []
        assert ctx.withheld_for_privacy >= 1


# ── M5 capture + no-training gate ───────────────────────────────────────


def test_capture_then_training_gated(db, monkeypatch):
    with _con(db) as con:
        p = project.create_project(
            con, title="Dad's biography",
            interview_guide={"must_cover": [{"id": "q1", "text": "Earliest memory?"}]},
        )
    s = ai.start_async_interview(db, project_id=p.project_id, informant_handle="a")
    with _con(db) as con:
        record_consent(con, interview_id=s.interview_id, scopes=[ConsentScope.RECORD])
    ai.submit_answer(db, interview_id=s.interview_id, question_id="q1",
                     transcript="The smell of his workshop in winter.", embedder=StubEmbedding())
    ai.next_followups(db, interview_id=s.interview_id)

    # Capture is always allowed (recording, not training).
    events = interviewer_capture.capture_trajectory(db, s.interview_id)
    assert any(e["role"] == "interviewer" for e in events)

    # A harvest/training attempt is refused while Loop 3 is locked.
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    with pytest.raises(Loop3UnlockRequired):
        interviewer_capture.harvest_for_rl(db, s.interview_id)

    # With the operator's explicit unlock, harvest proceeds.
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")
    harvested = interviewer_capture.harvest_for_rl(db, s.interview_id)
    assert harvested.investigation_id.endswith(s.interview_id)
