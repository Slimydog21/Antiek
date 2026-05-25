"""Speak SPR-03 — multi-interviewee project + invitation system tests.

Covers the rigor #3 enumeration: a declined invite, an incomplete
interview, the same person invited twice (dedupe), a public-intent
project (publish-scope consent at invite), and project-scope isolation
(one project's graph must not bleed into another).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.speak import async_interview as ai
from substrate.speak import invitations, project
from substrate.speak.consent import ConsentScope
from substrate.speak.invitations import PublicEcosystemGated
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-project-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="speak_project_test_setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="speak_project_test")


# ── M1 project model ────────────────────────────────────────────────────


def test_create_project(db):
    with _con(db) as con:
        p = project.create_project(
            con, title="Dad's biography", subject_ref="the-dad",
            subject_status="deceased", publish_intent="will_be_public",
        )
        assert p.publish_intent == "will_be_public"
        assert p.subject_status == "deceased"
        got = project.get_project(con, p.project_id)
        assert got.title == "Dad's biography"


def test_project_scoped_claims_only_that_project(db):
    with _con(db) as con:
        a = project.create_project(con, title="A")
        b = project.create_project(con, title="B")
        record_claim(con, project_id=a.project_id, text="A fact about A.", interview_id="iv-a")
        record_claim(con, project_id=b.project_id, text="A fact about B.", interview_id="iv-b")
        a_claims = project.project_claims(con, a.project_id)
        assert len(a_claims) == 1
        assert a_claims[0].project_id == a.project_id


# ── M2 invitation system ────────────────────────────────────────────────


def test_invite_n_stakeholders_creates_n_links(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        invites = [
            invitations.invite_stakeholder(con, project_id=p.project_id, informant_email=f"f{i}@x.com")
            for i in range(3)
        ]
        links = {iv.link for iv in invites}
        assert len(links) == 3
        for iv in invites:
            assert iv.link.startswith("https://interview.antiek.ai/")
            assert "?token=" in iv.link
            assert iv.status == "invited"


def test_invite_dedupes_same_email(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        a = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="dup@x.com")
        b = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="dup@x.com")
        assert a.interview_id == b.interview_id


def test_resolve_token_round_trips(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        iv = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="a@x.com")
        resolved = invitations.resolve_token(con, iv.token)
        assert resolved is not None
        assert resolved.interview_id == iv.interview_id
        assert invitations.resolve_token(con, "not-a-real-token") is None


def test_lifecycle_tracked(db):
    p_id = None
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        p_id = p.project_id
        i_decline = invitations.invite_stakeholder(con, project_id=p_id, informant_email="d@x.com")
        i_abandon = invitations.invite_stakeholder(con, project_id=p_id, informant_email="a@x.com")
    ai.decline(db, i_decline.interview_id)
    ai.mark_incomplete(db, i_abandon.interview_id)
    with _con(db) as con:
        statuses = {row["interview_id"]: row["status"] for row in invitations.lifecycle(con, p_id)}
    assert statuses[i_decline.interview_id] == "declined"
    assert statuses[i_abandon.interview_id] == "incomplete"


# ── M3 public dimension gated G7 ────────────────────────────────────────


def test_public_contribution_gated_on_g7(db, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", raising=False)
    with _con(db) as con:
        p = project.create_project(con, title="Public biography")
        assert invitations.public_ecosystem_enabled() is False
        with pytest.raises(PublicEcosystemGated):
            invitations.open_public_contribution(con, p.project_id)


def test_public_contribution_works_when_g7_enabled(db, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    with _con(db) as con:
        p = project.create_project(con, title="Public biography")
        invitations.open_public_contribution(con, p.project_id)
        assert project.get_project(con, p.project_id).invitation_mode == "public"


# ── M4 scoped consent at invite ─────────────────────────────────────────


def test_public_project_invite_requires_publish_scope(db):
    with _con(db) as con:
        p = project.create_project(con, title="Public bio", publish_intent="will_be_public")
        iv = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="a@x.com")
        assert ConsentScope.PUBLISH in iv.required_consent_scopes


def test_private_project_invite_requires_only_record(db):
    with _con(db) as con:
        p = project.create_project(con, title="Private bio", publish_intent="private_never_published")
        iv = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="a@x.com")
        assert iv.required_consent_scopes == (ConsentScope.RECORD,)


# ── M5 project-scoped aggregation + isolation ───────────────────────────


def test_aggregation_attributes_to_interviewee(db):
    with _con(db) as con:
        p = project.create_project(con, title="Dad's biography")
        iv1 = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="a@x.com")
        iv2 = invitations.invite_stakeholder(con, project_id=p.project_id, informant_email="b@x.com")
        record_claim(con, project_id=p.project_id, text="He was generous.", interview_id=iv1.interview_id)
        record_claim(con, project_id=p.project_id, text="He loved music.", interview_id=iv1.interview_id)
        record_claim(con, project_id=p.project_id, text="He told great stories.", interview_id=iv2.interview_id)
        contribs = project.contributions_by_interviewee(con, p.project_id)
        assert contribs[iv1.interview_id] == 2
        assert contribs[iv2.interview_id] == 1


def test_project_isolation_no_cross_bleed(db):
    with _con(db) as con:
        a = project.create_project(con, title="A")
        b = project.create_project(con, title="B")
        record_claim(con, project_id=a.project_id, text="A-only fact.", interview_id="iv-a")
        # Query project B → must not see A's claim.
        assert project.project_claims(con, b.project_id) == []
        assert project.contributions_by_interviewee(con, b.project_id) == {}
