"""Speak REST surface — end-to-end journey + gate-refusal tests.

Exercises the wired router (via the real create_app) over a tmp DB: the
full operator + invitee journey from project creation to a public,
corroborated, monetised publication + a physical-book quote — and that
every gate refuses with the right HTTP status. This is the test that
lets the speak-biography e2e un-skip: the surface now exists.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-api-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    # Open auth (operator env unset) + hermetic embedding for the
    # voice-note answer ingest.
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.setattr("acquisition.voice.adapter.default_embedding_provider",
                        lambda: StubEmbedding())
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def _invite_and_attest(client, project_id, email, claim_text, subject="the-dad"):
    """Invite an interviewee, consent, and record one third-party claim."""
    iv = client.post(f"/speak/projects/{project_id}/invites",
                     json={"informant_email": email}).json()
    interview_id = iv["interview_id"]
    r = client.post(f"/speak/interviews/{interview_id}/consent",
                    json={"scopes": ["record", "attribute", "publish"]})
    assert r.status_code == 200
    r = client.post(f"/speak/interviews/{interview_id}/claims",
                    json={"text": claim_text, "about_subject": True, "subject_ref": subject})
    assert r.status_code == 201, r.text
    return interview_id


# ── full journey ────────────────────────────────────────────────────────


def test_full_operator_journey_to_public_publish(client, monkeypatch):
    # 1. Create a will-be-public project about a deceased subject.
    r = client.post("/speak/projects", json={
        "title": "Dad's biography", "subject_ref": "the-dad",
        "subject_status": "deceased", "publish_intent": "will_be_public",
    })
    assert r.status_code == 201, r.text
    project_id = r.json()["project_id"]

    # 2. Economics: public ⇒ algorithmic split, 10% margin.
    econ = client.get(f"/speak/projects/{project_id}/economics").json()
    assert econ["split_applies"] is True
    assert econ["inference_margin"] == "0.10"

    # 3. Invite two interviewees who independently attest the same claim.
    iv1 = _invite_and_attest(client, project_id, "a@x.com", "He ran the village bakery for thirty years.")
    _invite_and_attest(client, project_id, "b@x.com", "He ran the village bakery for thirty years.")

    # 4. Invite token resolves (the landing flow).
    invites = client.get(f"/speak/projects/{project_id}/invites").json()
    assert invites["count"] == 2

    # 5. A voice-note answer ingests (hermetic embedding stub).
    r = client.post(f"/speak/interviews/{iv1}/answers",
                    json={"question_id": "q1", "transcript": "He baked bread before dawn every day."})
    assert r.status_code == 201, r.text
    assert r.json()["document_id"]

    # 6. Corroborate → the shared claim is multiply-attested.
    clusters = client.post(f"/speak/projects/{project_id}/corroborate").json()["clusters"]
    assert any(c["label"] == "multiply_attested" for c in clusters)

    # 7. Subject consent (deceased → documented rule).
    r = client.post(f"/speak/projects/{project_id}/subject-consent", json={
        "subject_ref": "the-dad", "subject_status": "deceased",
        "consent_granted": False, "rationale": "deceased 2019; documented rule.",
    })
    assert r.status_code == 200

    # 8. Map an interviewee to a payee.
    r = client.post(f"/speak/projects/{project_id}/contributors",
                    json={"interview_id": iv1, "display_name": "A"})
    assert r.status_code == 201

    # 9. Draft (public) — the corroborated claim is included, none excluded.
    draft = client.post(f"/speak/projects/{project_id}/draft", json={"public": True}).json()
    assert "bakery" in draft["prose_text"]
    assert draft["excluded_claim_ids"] == []

    # 10. Publish (gate closed via env) → served as platform_authored, split accrues.
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    r = client.post(f"/speak/projects/{project_id}/publish", json={"ad_revenue_usd": "100"})
    assert r.status_code == 201, r.text
    pub = r.json()
    assert pub["served"] is True
    assert pub["servability"] == "platform_authored"
    assert len(pub["accrual_lines"]) >= 1

    # 11. Physical-book quote — split economics persist, never fulfilled.
    r = client.post(f"/speak/projects/{project_id}/book-orders",
                    json={"book_format": "paperback", "page_count": 200})
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["payer"] == "split"
    assert order["fulfilled"] is False


# ── gate refusals (the load-bearing ones) ───────────────────────────────


def test_publish_refused_when_legal_gate_open(client, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    r = client.post("/speak/projects", json={
        "title": "Bio", "subject_ref": "x", "subject_status": "deceased",
        "publish_intent": "will_be_public",
    })
    project_id = r.json()["project_id"]
    client.post(f"/speak/projects/{project_id}/subject-consent", json={
        "subject_ref": "x", "subject_status": "deceased",
        "consent_granted": False, "rationale": "documented.",
    })
    r = client.post(f"/speak/projects/{project_id}/publish", json={})
    assert r.status_code == 409
    assert "legal gate" in r.json()["detail"] or "G2" in r.json()["detail"]


def test_open_public_refused_without_g7(client, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", raising=False)
    pid = client.post("/speak/projects", json={"title": "Bio"}).json()["project_id"]
    r = client.post(f"/speak/projects/{pid}/open-public")
    assert r.status_code == 403


def test_answer_before_consent_refused(client):
    pid = client.post("/speak/projects", json={"title": "Bio"}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    r = client.post(f"/speak/interviews/{iv['interview_id']}/answers",
                    json={"question_id": "q1", "transcript": "answer before consent"})
    assert r.status_code == 403


def test_resolve_unknown_token_404(client):
    r = client.get("/speak/invites/resolve", params={"token": "nope"})
    assert r.status_code == 404


def test_private_publish_not_served(client):
    pid = client.post("/speak/projects", json={
        "title": "Private bio", "publish_intent": "private_never_published",
    }).json()["project_id"]
    r = client.post(f"/speak/projects/{pid}/publish", json={})
    assert r.status_code == 201, r.text
    assert r.json()["served"] is False
    assert r.json()["visibility"] == "private"


def _token_from_link(link: str) -> str:
    return link.split("token=", 1)[1]


def test_invitee_token_flow(client):
    # Operator creates a will-be-public project + invites someone.
    project_id = client.post("/speak/projects", json={
        "title": "Dad's biography", "subject_ref": "the-dad",
        "subject_status": "deceased", "publish_intent": "will_be_public",
    }).json()["project_id"]
    iv = client.post(f"/speak/projects/{project_id}/invites",
                     json={"informant_email": "aunt@x.com"}).json()
    token = _token_from_link(iv["link"])

    # The invitee lands via their TOKEN (no operator account).
    landing = client.get(f"/speak/invite/{token}").json()
    assert landing["project_title"] == "Dad's biography"
    assert "publish" in landing["required_consent_scopes"]
    assert landing["granted_consent_scopes"] == []  # nothing granted yet

    # They grant scoped consent (record only — declining publish is allowed).
    r = client.post(f"/speak/invite/{token}/consent", json={"scopes": ["record"]})
    assert r.status_code == 200
    assert "record" in r.json()["granted"]

    # Now they can answer; the text they submit is the (corrected) transcript.
    r = client.post(f"/speak/invite/{token}/answer",
                    json={"question_id": "q1", "transcript": "He taught me to bake bread before dawn."})
    assert r.status_code == 201, r.text

    # The landing reflects their contribution.
    landing2 = client.get(f"/speak/invite/{token}").json()
    assert "record" in landing2["granted_consent_scopes"]
    assert any("bread" in t["text"] for t in landing2["transcript"])


def test_invitee_answer_requires_consent(client):
    pid = client.post("/speak/projects", json={"title": "Bio"}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    token = _token_from_link(iv["link"])
    # Answer before consent → 403 (ConsentRequired surfaced).
    r = client.post(f"/speak/invite/{token}/answer",
                    json={"question_id": "q1", "transcript": "before consent"})
    assert r.status_code == 403


def test_invitee_bad_token_404(client):
    assert client.get("/speak/invite/not-a-real-token").status_code == 404
    assert client.post("/speak/invite/not-a-real-token/consent",
                       json={"scopes": ["record"]}).status_code == 404
    assert client.post("/speak/invite/not-a-real-token/answer",
                       json={"question_id": "q", "transcript": "x"}).status_code == 404


def test_invitee_surface_open_while_operator_endpoints_authed(client, monkeypatch):
    # Turn operator auth ON. The operator surface must require auth; the
    # token-gated invitee surface must still be REACHABLE (token is the
    # credential), returning 404 for a bad token rather than an auth 401.
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "secret-operator-token")
    operator_resp = client.get("/speak/projects")
    assert operator_resp.status_code in (401, 403), "operator endpoint must be auth-gated"
    invitee_resp = client.get("/speak/invite/some-token")
    assert invitee_resp.status_code not in (401, 403), "invitee surface must be open (token-gated)"
    assert invitee_resp.status_code == 404  # reached the endpoint; token invalid


def test_invitee_decline(client):
    pid = client.post("/speak/projects", json={"title": "Bio"}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    token = _token_from_link(iv["link"])
    r = client.post(f"/speak/invite/{token}/decline")
    assert r.status_code == 200
    assert r.json()["status"] == "declined"


class _StubWhisper:
    """Transcribes anything to a fixed string — hermetic, no API key."""
    def __init__(self, *a, **k):
        pass

    def transcribe(self, audio_bytes, *, filename, language=None):
        class _T:
            text = "He taught me to bake bread before dawn."
        return _T()


class _NoKeyWhisper:
    def __init__(self, *a, **k):
        pass

    def transcribe(self, *a, **k):
        raise RuntimeError("OPENAI_API_KEY not set; cannot call whisper.")


class _FailWhisper:
    def __init__(self, *a, **k):
        pass

    def transcribe(self, *a, **k):
        raise RuntimeError("whisper backend exploded")


def _invite_token(client, **proj):
    pid = client.post("/speak/projects", json={"title": "Bio", **proj}).json()["project_id"]
    iv = client.post(f"/speak/projects/{pid}/invites", json={"informant_email": "a@x.com"}).json()
    return _token_from_link(iv["link"])


def test_invitee_transcribe_returns_raw_text(client, monkeypatch):
    monkeypatch.setattr("acquisition.voice.WhisperTranscriber", _StubWhisper)
    token = _invite_token(client)
    r = client.post(f"/speak/invite/{token}/transcribe",
                    content=b"\x00\x01fake-webm-audio",
                    headers={"Content-Type": "audio/webm"})
    assert r.status_code == 200, r.text
    assert "bread" in r.json()["transcript"]  # raw; the invitee then corrects + submits


def test_invitee_transcribe_bad_token_404(client, monkeypatch):
    monkeypatch.setattr("acquisition.voice.WhisperTranscriber", _StubWhisper)
    r = client.post("/speak/invite/not-a-token/transcribe", content=b"audio",
                    headers={"Content-Type": "audio/webm"})
    assert r.status_code == 404


def test_invitee_transcribe_empty_body_400(client, monkeypatch):
    monkeypatch.setattr("acquisition.voice.WhisperTranscriber", _StubWhisper)
    token = _invite_token(client)
    r = client.post(f"/speak/invite/{token}/transcribe", content=b"",
                    headers={"Content-Type": "audio/webm"})
    assert r.status_code == 400


def test_invitee_transcribe_unconfigured_503(client, monkeypatch):
    # No OPENAI_API_KEY → 503 so the UI falls back to typing.
    monkeypatch.setattr("acquisition.voice.WhisperTranscriber", _NoKeyWhisper)
    token = _invite_token(client)
    r = client.post(f"/speak/invite/{token}/transcribe", content=b"audio",
                    headers={"Content-Type": "audio/webm"})
    assert r.status_code == 503


def test_invitee_transcribe_failure_422(client, monkeypatch):
    monkeypatch.setattr("acquisition.voice.WhisperTranscriber", _FailWhisper)
    token = _invite_token(client)
    r = client.post(f"/speak/invite/{token}/transcribe", content=b"audio",
                    headers={"Content-Type": "audio/webm"})
    assert r.status_code == 422


def test_list_projects(client):
    # Fresh DB → empty list.
    r = client.get("/speak/projects")
    assert r.status_code == 200
    assert r.json()["count"] == 0
    # Create two → both listed with their publish intent + interview count.
    client.post("/speak/projects", json={"title": "Dad's biography"})
    client.post("/speak/projects", json={"title": "Mom's biography", "publish_intent": "will_be_public"})
    data = client.get("/speak/projects").json()
    assert data["count"] == 2
    titles = {p["title"] for p in data["projects"]}
    assert titles == {"Dad's biography", "Mom's biography"}
    assert all("interview_count" in p and "publish_intent" in p for p in data["projects"])
