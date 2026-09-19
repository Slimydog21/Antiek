"""Speak re-ping email seam — consent-scoped AgentMail/Resend delivery."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.auth.email_provider import MockEmailProvider, get_email_provider
from substrate.speak import reping_mail


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-reping-mail-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTIEK_SPEAK_REPING_EMAIL", raising=False)
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "mock")
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    # Fresh mock provider per test so .sent is isolated.
    mock = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr(
        "substrate.speak.reping_mail.get_email_provider",
        lambda: mock,
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    client = TestClient(app)
    client._mock_mail = mock  # type: ignore[attr-defined]
    return client


def _invite_friend(client, email="friend@x.com"):
    priv = client.post(
        "/speak/projects",
        json={"title": "Dad bio", "publish_intent": "private_never_published"},
    ).json()
    iv = client.post(
        f"/speak/projects/{priv['project_id']}/invites",
        json={"informant_email": email},
    ).json()
    return priv, iv


def test_reping_email_skipped_when_env_gate_off(client):
    _, iv = _invite_friend(client)
    r = client.post(
        "/speak/pushes/reping",
        json={"interview_id": iv["interview_id"], "send_email": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_reason"] is None
    assert body["email_status"] == "skipped_env_gate"
    assert client._mock_mail.sent == []


def test_reping_email_sent_when_env_gate_on(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_REPING_EMAIL", "1")
    _, iv = _invite_friend(client, email="aunt@x.com")
    r = client.post(
        "/speak/pushes/reping",
        json={"interview_id": iv["interview_id"], "send_email": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email_status"] == "sent"
    assert body["email_to"] == "aunt@x.com"
    assert body["email_provider"] == "mock"
    assert len(client._mock_mail.sent) == 1
    mail = client._mock_mail.sent[0].email
    assert mail.to == "aunt@x.com"
    assert f"/speak/invite/{iv['token']}" in mail.text_body or iv["token"] in mail.text_body
    assert "antiek.ai/speak/invite" in mail.text_body


def test_reping_never_emails_declined(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_REPING_EMAIL", "1")
    _, iv = _invite_friend(client, email="nope@x.com")
    assert client.post(f"/speak/invite/{iv['token']}/decline").status_code == 200
    r = client.post(
        "/speak/pushes/reping",
        json={"interview_id": iv["interview_id"], "send_email": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert "declined" in (body["skipped_reason"] or "")
    assert body["email_status"] == "skipped_declined"
    assert client._mock_mail.sent == []


def test_reping_degrades_when_credentials_missing(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_REPING_EMAIL", "1")
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "agentmail")
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
    monkeypatch.delenv("ANTIEK_AGENTMAIL_INBOX_ID", raising=False)
    # Use real factory so AgentMail raises EmailDeliveryFailure
    monkeypatch.setattr(
        "substrate.speak.reping_mail.get_email_provider",
        get_email_provider,
    )
    _, iv = _invite_friend(client)
    r = client.post(
        "/speak/pushes/reping",
        json={"interview_id": iv["interview_id"], "send_email": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email_status"] == "degraded_credentials_or_transport"
    assert body["invite_path"]  # door still returned
    assert "AGENTMAIL" in (body["email_detail"] or "")


def test_try_send_unit_not_requested():
    r = reping_mail.try_send_reping_email(
        to="a@x.com",
        invite_path="/speak/invite/t",
        project_title="T",
        followups_added=0,
        pending_question_count=1,
        send_requested=False,
    )
    assert r.status == "skipped_not_requested"
