"""Speak SPR-01 — consent & rights gate tests.

The legal spine, enforced at the data layer (these tests bypass the UI
entirely). Covers the rigor #3 enumeration: an interviewee who consents
to record but not publish; a claim about a non-consenting third party; a
deceased vs. living subject; takedown after publish (purge); and a claim
some attest while the gate stays closed.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_interview, insert_interview_project
from substrate.graph.schema import init_database
from substrate.speak import consent as consent_mod
from substrate.speak import publish_gate, subject_consent, takedown, third_party
from substrate.speak.consent import ConsentScope, ScopedConsentRequired
from substrate.speak.publish_gate import PublishBlocked
from substrate.speak.schema import ensure_speak_schema


@pytest.fixture
def speak_db(monkeypatch):
    """Tmp DuckDB with the base + Speak schema, one project + one
    interview, and an isolated events dir."""
    tmpdir = tempfile.mkdtemp(prefix="speak-consent-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    con = connect_write(db_path, purpose="speak_consent_test")
    init_database(con)
    ensure_speak_schema(con)
    project_id = insert_interview_project(con, title="Dad's biography", project_id="proj-dad")
    interview_id = insert_interview(con, project_id=project_id, informant_handle="uncle-fawzi")
    try:
        yield {"con": con, "project_id": project_id, "interview_id": interview_id}
    finally:
        con.close()


# ── M1 scoped consent ──────────────────────────────────────────────────


def test_record_scope_only_does_not_grant_publish(speak_db):
    con, iv = speak_db["con"], speak_db["interview_id"]
    consent_mod.record_consent(con, interview_id=iv, scopes=[ConsentScope.RECORD])
    state = consent_mod.consent_state(con, iv)
    assert state.has(ConsentScope.RECORD)
    assert not state.has(ConsentScope.PUBLISH)
    assert not state.has(ConsentScope.ATTRIBUTE)
    # require_consent enforces the right scope per action.
    consent_mod.require_consent(con, iv, ConsentScope.RECORD, action="ask_question")
    with pytest.raises(ScopedConsentRequired):
        consent_mod.require_consent(con, iv, ConsentScope.PUBLISH, action="publish_public")
    with pytest.raises(ScopedConsentRequired):
        consent_mod.require_consent(con, iv, ConsentScope.ATTRIBUTE, action="attribute_by_name")


def test_record_consent_bridges_legacy_boolean(speak_db):
    con, iv = speak_db["con"], speak_db["interview_id"]
    consent_mod.record_consent(con, interview_id=iv, scopes=[ConsentScope.RECORD])
    flag = con.execute(
        "SELECT consent_recorded FROM interviews WHERE interview_id = ?", [iv]
    ).fetchone()[0]
    assert flag is True  # the orchestrator gate sees consent


def test_revoke_consent_removes_scope(speak_db):
    con, iv = speak_db["con"], speak_db["interview_id"]
    consent_mod.record_consent(con, interview_id=iv, scopes=[ConsentScope.RECORD, ConsentScope.PUBLISH])
    consent_mod.revoke_consent(con, interview_id=iv, scopes=[ConsentScope.PUBLISH])
    state = consent_mod.consent_state(con, iv)
    assert state.has(ConsentScope.RECORD)
    assert not state.has(ConsentScope.PUBLISH)


# ── M2 third-party tagging ──────────────────────────────────────────────


def test_claim_about_subject_is_tagged_third_party(speak_db):
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    claim = third_party.record_claim(
        con, project_id=proj, interview_id=iv,
        text="My father risked his life to save a stranger.",
        about_subject=True, subject_ref="the-dad",
    )
    assert claim.is_third_party is True
    assert claim.verification == "unverified"


def test_first_party_claim_not_third_party(speak_db):
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    claim = third_party.record_claim(
        con, project_id=proj, interview_id=iv,
        text="I felt nervous the day I met him.", about_subject=False,
    )
    assert claim.is_third_party is False


# ── M3 verification-before-publish (bypassing the UI) ───────────────────


def test_uncorroborated_third_party_claim_blocked(speak_db):
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    claim = third_party.record_claim(
        con, project_id=proj, interview_id=iv,
        text="His business partner embezzled the company.",
        about_subject=False, subject_ref="the-partner",
    )
    with pytest.raises(PublishBlocked):
        publish_gate.assert_claim_publishable(con, claim.claim_id)


def test_operator_attested_third_party_claim_publishable(speak_db):
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    claim = third_party.record_claim(
        con, project_id=proj, interview_id=iv,
        text="He emigrated in 1971.", about_subject=True, subject_ref="the-dad",
    )
    publish_gate.operator_attest_claim(con, claim.claim_id, project_id=proj)
    publish_gate.assert_claim_publishable(con, claim.claim_id)  # no raise


def test_contradicted_claim_never_publishable(speak_db):
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    claim = third_party.record_claim(
        con, project_id=proj, interview_id=iv,
        text="He was born in Cairo.", about_subject=True, subject_ref="the-dad",
    )
    con.execute(
        "UPDATE speak_claims SET verification = 'contradicted' WHERE claim_id = ?",
        [claim.claim_id],
    )
    with pytest.raises(PublishBlocked):
        publish_gate.assert_claim_publishable(con, claim.claim_id)


def test_first_party_claim_publishable_without_corroboration(speak_db):
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    claim = third_party.record_claim(
        con, project_id=proj, interview_id=iv,
        text="I remember the smell of his workshop.", about_subject=False,
    )
    publish_gate.assert_claim_publishable(con, claim.claim_id)  # no raise


# ── M4 subject consent (living vs deceased) ─────────────────────────────


def test_living_subject_requires_consent(speak_db):
    con, proj = speak_db["con"], speak_db["project_id"]
    subject_consent.record_subject_consent(
        con, project_id=proj, subject_ref="the-dad",
        subject_status="living", consent_granted=False,
    )
    d = subject_consent.public_publish_allowed_for_subject(con, project_id=proj, subject_ref="the-dad")
    assert d.allowed is False


def test_deceased_subject_allowed_with_rationale(speak_db):
    con, proj = speak_db["con"], speak_db["project_id"]
    subject_consent.record_subject_consent(
        con, project_id=proj, subject_ref="the-dad",
        subject_status="deceased", consent_granted=False,
        rationale="Subject deceased 2019; no living-person right-of-publicity.",
    )
    d = subject_consent.public_publish_allowed_for_subject(con, project_id=proj, subject_ref="the-dad")
    assert d.allowed is True


def test_deceased_subject_blocked_without_rationale(speak_db):
    con, proj = speak_db["con"], speak_db["project_id"]
    subject_consent.record_subject_consent(
        con, project_id=proj, subject_ref="the-dad",
        subject_status="deceased", consent_granted=False, rationale=None,
    )
    d = subject_consent.public_publish_allowed_for_subject(con, project_id=proj, subject_ref="the-dad")
    assert d.allowed is False


def test_unrecorded_subject_treated_as_living(speak_db):
    con, proj = speak_db["con"], speak_db["project_id"]
    d = subject_consent.public_publish_allowed_for_subject(con, project_id=proj, subject_ref="nobody")
    assert d.allowed is False


# ── M5 takedown ─────────────────────────────────────────────────────────


def test_takedown_purges_served_publication(speak_db):
    con, proj = speak_db["con"], speak_db["project_id"]
    con.execute(
        "INSERT INTO speak_publications (publication_id, project_id, visibility, served) "
        "VALUES ('pub-1', ?, 'public', TRUE)",
        [proj],
    )
    takedown.request_takedown(con, project_id=proj, target_kind="interview",
                              target_id=speak_db["interview_id"], reason="requester withdrew")
    row = con.execute(
        "SELECT served, taken_down FROM speak_publications WHERE publication_id = 'pub-1'"
    ).fetchone()
    assert row[0] is False and row[1] is True


def test_takedown_blocks_claim_publish(speak_db):
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    claim = third_party.record_claim(
        con, project_id=proj, interview_id=iv,
        text="He won an award in 1985.", about_subject=True, subject_ref="the-dad",
    )
    publish_gate.operator_attest_claim(con, claim.claim_id, project_id=proj)
    publish_gate.assert_claim_publishable(con, claim.claim_id)  # publishable before takedown
    takedown.request_takedown(con, project_id=proj, target_kind="interview", target_id=iv)
    with pytest.raises(PublishBlocked):
        publish_gate.assert_claim_publishable(con, claim.claim_id)


def test_takedown_reversible(speak_db):
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    tid = takedown.request_takedown(con, project_id=proj, target_kind="interview", target_id=iv)
    assert takedown.is_taken_down(con, target_kind="interview", target_id=iv) is True
    takedown.reverse_takedown(con, takedown_id=tid, project_id=proj)
    assert takedown.is_taken_down(con, target_kind="interview", target_id=iv) is False


# ── M6 public-publishing gate (G2/G3) ───────────────────────────────────


def test_public_publish_refused_with_legal_gate_open(speak_db, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    con, proj = speak_db["con"], speak_db["project_id"]
    d = publish_gate.check_public_publish(con, project_id=proj)
    assert d.allowed is False
    assert "legal gate" in d.reason or "G2" in d.reason


def test_public_publish_refused_without_subject_consent(speak_db, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")  # G2/G3 "closed"
    con, proj = speak_db["con"], speak_db["project_id"]
    # Project has a living subject with no consent.
    con.execute(
        "INSERT INTO speak_projects (project_id, publish_intent, subject_ref, subject_status) "
        "VALUES (?, 'will_be_public', 'the-dad', 'living')",
        [proj],
    )
    subject_consent.record_subject_consent(
        con, project_id=proj, subject_ref="the-dad",
        subject_status="living", consent_granted=False,
    )
    d = publish_gate.check_public_publish(con, project_id=proj)
    assert d.allowed is False


def test_public_publish_allowed_when_all_gates_satisfied(speak_db, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    con.execute(
        "INSERT INTO speak_projects (project_id, publish_intent, subject_ref, subject_status) "
        "VALUES (?, 'will_be_public', 'the-dad', 'deceased')",
        [proj],
    )
    subject_consent.record_subject_consent(
        con, project_id=proj, subject_ref="the-dad", subject_status="deceased",
        consent_granted=False, rationale="deceased 2019; documented rule.",
    )
    # One third-party claim, operator-attested → publishable.
    claim = third_party.record_claim(
        con, project_id=proj, interview_id=iv,
        text="He emigrated in 1971.", about_subject=True, subject_ref="the-dad",
    )
    publish_gate.operator_attest_claim(con, claim.claim_id, project_id=proj)
    d = publish_gate.check_public_publish(con, project_id=proj)
    assert d.allowed is True, d.reason


def test_public_publish_blocked_by_uncorroborated_claim(speak_db, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    con, proj, iv = speak_db["con"], speak_db["project_id"], speak_db["interview_id"]
    con.execute(
        "INSERT INTO speak_projects (project_id, publish_intent, subject_ref, subject_status) "
        "VALUES (?, 'will_be_public', 'the-dad', 'deceased')",
        [proj],
    )
    subject_consent.record_subject_consent(
        con, project_id=proj, subject_ref="the-dad", subject_status="deceased",
        consent_granted=False, rationale="deceased; documented rule.",
    )
    third_party.record_claim(
        con, project_id=proj, interview_id=iv,
        text="He secretly funded a rival.", about_subject=True, subject_ref="the-dad",
    )  # left unverified
    d = publish_gate.check_public_publish(con, project_id=proj)
    assert d.allowed is False
    assert len(d.blocked_claim_ids) == 1
