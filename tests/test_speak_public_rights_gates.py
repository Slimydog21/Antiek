"""Speak public-output rights gates: interviewee publish consent, the
project's own subject, and takedown on the public opportunities list.

Three holes in the same spine, each driven through the real route:

* ``check_public_publish`` never read ``speak_consent``. An interviewee who
  granted only ``record`` (the invite page's default button) was published
  publicly and accrued a share, and ``generate_draft(public=True)`` put
  their words in the public draft. ``require_consent`` had no production
  caller.
* The subject-consent step took ``subject_ref`` from the POST body, so a
  caller could have the gate check a stand-in subject, and it skipped the
  check entirely when the project names no subject (deny-by-default says
  an unknown subject is treated as living).
* ``GET /speak/opportunities`` is unauthenticated and returns
  ``subject_ref``; ``/speak/feed`` hides a project under active takedown,
  the opportunities list did not.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import reset_auth_throttles
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.speak import biography, project, publish_gate, subject_consent
from substrate.speak.consent import ConsentScope, record_consent, revoke_consent
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    tmpdir = tempfile.mkdtemp(prefix="speak-rights-gates-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> str:
    tmpdir = tempfile.mkdtemp(prefix="speak-rights-gates-db-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _deceased_public_project(client: TestClient, subject: str = "the-dad") -> str:
    r = client.post("/speak/projects", json={
        "title": "Dad's biography", "subject_ref": subject,
        "subject_status": "deceased", "publish_intent": "will_be_public",
    })
    assert r.status_code == 201, r.text
    pid = str(r.json()["project_id"])
    r = client.post(f"/speak/projects/{pid}/subject-consent", json={
        "subject_ref": subject, "subject_status": "deceased",
        "consent_granted": False, "rationale": "deceased 2019; documented rule.",
    })
    assert r.status_code == 200, r.text
    return pid


def _interviewee(client: TestClient, pid: str, email: str, scopes: list[str]) -> str:
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": email}).json()
    interview_id = str(iv["interview_id"])
    r = client.post(f"/speak/interviews/{interview_id}/consent", json={"scopes": scopes})
    assert r.status_code == 200, r.text
    # A first-party claim: no corroboration needed, so only consent can stop it.
    r = client.post(f"/speak/interviews/{interview_id}/claims",
                    json={"text": "I baked bread with him every Sunday.", "about_subject": False})
    assert r.status_code == 201, r.text
    return interview_id


# ── W19: interviewee publish-scope consent ──────────────────────────────


def test_record_only_interviewee_blocks_public_publish(client, monkeypatch):
    pid = _deceased_public_project(client)
    iv = _interviewee(client, pid, "friend@x.com", ["record", "attribute"])
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")

    r = client.post(f"/speak/projects/{pid}/publish", json={"ad_revenue_usd": "100"})
    assert r.status_code == 409, (
        "an interviewee who granted only record+attribute was published "
        f"publicly: {r.status_code} {r.text}"
    )
    assert iv in r.json()["detail"]


def test_publish_scope_interviewee_publishes(client, monkeypatch):
    """Control: the same project, publish granted, still publishes."""
    pid = _deceased_public_project(client)
    iv = _interviewee(client, pid, "friend@x.com", ["record", "attribute", "publish"])
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")

    r = client.post(f"/speak/projects/{pid}/publish", json={"ad_revenue_usd": "100"})
    assert r.status_code == 201, r.text
    assert r.json()["served"] is True
    assert [a["interview_id"] for a in r.json()["accrual_lines"]] in ([], [iv])


def test_revoked_publish_consent_blocks_the_gate(db, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    with connect_write(db, purpose="rights_gate_test") as con:
        p = project.create_project(con, title="Bio", subject_ref="the-dad",
                                   subject_status="deceased", publish_intent="will_be_public")
        subject_consent.record_subject_consent(
            con, project_id=p.project_id, subject_ref="the-dad", subject_status="deceased",
            consent_granted=False, rationale="deceased 2019; documented rule.",
        )
        record_claim(con, project_id=p.project_id, interview_id="iv-a",
                     text="I learned to bake at his side.", about_subject=False)
        record_consent(con, interview_id="iv-a",
                       scopes=[ConsentScope.RECORD, ConsentScope.PUBLISH])
        assert publish_gate.check_public_publish(con, project_id=p.project_id).allowed

        revoke_consent(con, interview_id="iv-a", scopes=[ConsentScope.PUBLISH])
        d = publish_gate.check_public_publish(con, project_id=p.project_id)
        assert d.allowed is False, d.reason
        assert "iv-a" in d.reason


def test_public_draft_leaves_out_record_only_words(db):
    with connect_write(db, purpose="rights_gate_test") as con:
        p = project.create_project(con, title="Bio")
        kept = record_claim(con, project_id=p.project_id, interview_id="iv-yes",
                            text="He whistled while he kneaded.", about_subject=False)
        private = record_claim(con, project_id=p.project_id, interview_id="iv-no",
                               text="I baked bread with him every Sunday.", about_subject=False)
        record_consent(con, interview_id="iv-yes",
                       scopes=[ConsentScope.RECORD, ConsentScope.PUBLISH])
        record_consent(con, interview_id="iv-no", scopes=[ConsentScope.RECORD])
        outline = biography.assemble_outline(con, project_id=p.project_id)

        public = biography.generate_draft(con, project_id=p.project_id, outline=outline,
                                          public=True)
        assert "every Sunday" not in public.prose_text, public.prose_text
        assert "iv-no" not in public.cited_interview_ids
        # A consent exclusion is reported on its own. excluded_claim_ids
        # means "not corroborated", and the UI says exactly that about it.
        assert public.consent_excluded_claim_ids == (private.claim_id,)
        assert private.claim_id not in public.excluded_claim_ids
        assert "kneaded" in public.prose_text
        assert kept.claim_id not in public.excluded_claim_ids

        # The private draft is the operator's own; record scope is enough.
        private_draft = biography.generate_draft(con, project_id=p.project_id,
                                                 outline=outline, public=False)
        assert "every Sunday" in private_draft.prose_text


# ── W20: the subject is the project's, never the caller's ───────────────


def test_body_subject_ref_cannot_redirect_the_subject_gate(client, monkeypatch):
    r = client.post("/speak/projects", json={
        "title": "Alice", "subject_ref": "alice-living",
        "subject_status": "living", "publish_intent": "will_be_public",
    })
    pid = r.json()["project_id"]
    # A passing stand-in on the same project.
    r = client.post(f"/speak/projects/{pid}/subject-consent", json={
        "subject_ref": "someone-else", "subject_status": "non_identifiable",
        "consent_granted": False, "rationale": "composite character.",
    })
    assert r.status_code == 200
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")

    control = client.post(f"/speak/projects/{pid}/publish", json={})
    assert control.status_code == 409, control.text

    r = client.post(f"/speak/projects/{pid}/publish", json={"subject_ref": "someone-else"})
    assert r.status_code != 201, (
        f"a body subject_ref redirected the subject-consent gate: {r.text}"
    )
    assert r.status_code in (409, 422), r.text


@pytest.mark.parametrize("status", ["unknown", "living"])
def test_project_without_subject_ref_is_refused(client, monkeypatch, status):
    r = client.post("/speak/projects", json={
        "title": "No subject named", "subject_status": status,
        "publish_intent": "will_be_public",
    })
    pid = r.json()["project_id"]
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")

    r = client.post(f"/speak/projects/{pid}/publish", json={})
    assert r.status_code == 409, (
        f"a project naming no subject (status {status}) published publicly "
        f"with no subject consent: {r.status_code} {r.text}"
    )
    assert "subject" in r.json()["detail"]


# ── W21: takedown on the unauthenticated opportunities list ─────────────


def test_taken_down_project_leaves_opportunities_and_pushes(client):
    def _public(title: str, subject: str) -> str:
        r = client.post("/speak/projects", json={
            "title": title, "subject_ref": subject, "publish_intent": "will_be_public",
        })
        assert r.status_code == 201, r.text
        return str(r.json()["project_id"])

    gone = _public("Under takedown", "jane.doe@example.test")
    _public("Control", "bob.control@example.test")

    def _subjects(path: str) -> set[str]:
        body = client.get(path).json()
        return {o["subject_ref"] for o in body["public_opportunities"]}

    assert "jane.doe@example.test" in _subjects("/speak/opportunities")

    r = client.post(f"/speak/projects/{gone}/takedowns", json={
        "target_kind": "subject", "target_id": "jane.doe@example.test",
        "requested_by": "jane.doe@example.test", "reason": "subject withdrew",
    })
    assert r.status_code == 201, r.text

    for path in ("/speak/opportunities", "/speak/opportunities?interest=jane%20doe",
                 "/speak/pushes"):
        subjects = _subjects(path)
        assert "jane.doe@example.test" not in subjects, (
            f"{path} still discloses a subject under active takedown: {subjects}"
        )
        assert "bob.control@example.test" in subjects


@pytest.fixture
def fresh_throttles() -> Iterator[None]:
    # The open-contribute rate limit is process-global; start clean and leave
    # no hits behind for the next test file that counts them.
    reset_auth_throttles()
    yield
    reset_auth_throttles()


def test_taken_down_project_mints_no_open_contribution(client, monkeypatch, fresh_throttles):
    """The G7 open-contribute door is unauthenticated, and the invite landing
    page it mints a token for returns ``subject_ref``. A project under active
    takedown must not get a fresh door, or the takedown leaks back out."""
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")

    def _public(title: str, subject: str) -> str:
        r = client.post("/speak/projects", json={
            "title": title, "subject_ref": subject, "publish_intent": "will_be_public",
        })
        assert r.status_code == 201, r.text
        return str(r.json()["project_id"])

    gone = _public("Under takedown", "jane.doe@example.test")
    control = _public("Control", "bob.control@example.test")
    r = client.post(f"/speak/projects/{gone}/takedowns", json={
        "target_kind": "subject", "target_id": "jane.doe@example.test",
        "requested_by": "jane.doe@example.test", "reason": "subject withdrew",
    })
    assert r.status_code == 201, r.text

    r = client.post(f"/speak/projects/{gone}/open-contribute")
    assert r.status_code != 201, (
        "open-contribute minted an invite on a project under active takedown: "
        f"{r.status_code} {r.text}"
    )
    assert r.status_code == 403, r.text
    assert "token" not in r.json()
    assert "takedown" in r.json()["detail"]

    ok = client.post(f"/speak/projects/{control}/open-contribute")
    assert ok.status_code == 201, ok.text
    land = client.get(ok.json()["invite_path"]).json()
    assert land["subject_ref"] == "bob.control@example.test"
