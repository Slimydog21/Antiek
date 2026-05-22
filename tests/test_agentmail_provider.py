"""AgentMail email provider — substrate-side tests.

Verifies the provider:
- builds the correct request shape (URL, auth header, body fields)
- surfaces actionable errors when not configured
- handles AgentMail's specific error responses (429 rate limit, 4xx/5xx)
- the factory picks it up via ``ANTIEK_EMAIL_PROVIDER=agentmail``

Does NOT exercise the live AgentMail API.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from substrate.auth import (
    AgentMailEmailProvider,
    EmailDeliveryFailure,
    OutboundEmail,
    get_email_provider,
)


# ── Helpers ──────────────────────────────────────────────────────────


@contextmanager
def _mock_urlopen(monkeypatch, *, status_code: int, body: dict):
    """Intercept urllib.request.urlopen with a fake response.

    Captures the request that would have been sent so tests can
    inspect URL + headers + body.
    """
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["data"] = req.data
        captured["method"] = req.get_method()
        if status_code >= 400:
            raise urllib.error.HTTPError(
                req.full_url,
                status_code,
                "Error",
                hdrs={},
                fp=io.BytesIO(json.dumps(body).encode("utf-8")),
            )
        return FakeResponse(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    yield captured


# ── Configuration / error-mode tests ─────────────────────────────────


def test_send_refuses_without_api_key(monkeypatch):
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
    monkeypatch.setenv("ANTIEK_AGENTMAIL_INBOX_ID", "inb_test")
    p = AgentMailEmailProvider()
    with pytest.raises(EmailDeliveryFailure, match="AGENTMAIL_API_KEY"):
        p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))


def test_send_refuses_without_inbox_id(monkeypatch):
    monkeypatch.setenv("AGENTMAIL_API_KEY", "am_test_key")
    monkeypatch.delenv("ANTIEK_AGENTMAIL_INBOX_ID", raising=False)
    p = AgentMailEmailProvider()
    with pytest.raises(EmailDeliveryFailure, match="ANTIEK_AGENTMAIL_INBOX_ID"):
        p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))


def test_inbox_id_required_error_mentions_runbook(monkeypatch):
    monkeypatch.setenv("AGENTMAIL_API_KEY", "am_test_key")
    monkeypatch.delenv("ANTIEK_AGENTMAIL_INBOX_ID", raising=False)
    p = AgentMailEmailProvider()
    with pytest.raises(EmailDeliveryFailure, match="agentmail-setup.md"):
        p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))


# ── Request shape tests ──────────────────────────────────────────────


def test_send_posts_to_inbox_messages_send_path(monkeypatch):
    p = AgentMailEmailProvider(api_key="am_k", inbox_id="inb_abc123")
    with _mock_urlopen(monkeypatch, status_code=200, body={"message_id": "msg_xyz"}) as captured:
        p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))
    assert captured["url"] == "https://api.agentmail.to/inboxes/inb_abc123/messages/send"
    assert captured["method"] == "POST"


def test_send_uses_bearer_auth_header(monkeypatch):
    p = AgentMailEmailProvider(api_key="am_secret_key", inbox_id="inb_abc")
    with _mock_urlopen(monkeypatch, status_code=200, body={"message_id": "msg_1"}) as captured:
        p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))
    # urllib normalizes header names to title-case
    auth = captured["headers"].get("Authorization") or captured["headers"].get("authorization")
    assert auth == "Bearer am_secret_key"


def test_send_body_uses_agentmail_field_names(monkeypatch):
    """AgentMail uses `to`, `subject`, `text`, `html` — NOT `from`
    (the inbox is the sender) and NOT `body` or `plain_text`."""
    p = AgentMailEmailProvider(api_key="am_k", inbox_id="inb_abc")
    with _mock_urlopen(monkeypatch, status_code=200, body={"message_id": "msg_1"}) as captured:
        p.send(OutboundEmail(
            to="recipient@example.com",
            subject="Sign in to Antiek",
            text_body="Click here: https://...",
            html_body="<p>Click <a href='...'>here</a></p>",
            from_addr="ignored-by-agentmail@x.com",
        ))
    body = json.loads(captured["data"].decode("utf-8"))
    assert body == {
        "to": "recipient@example.com",
        "subject": "Sign in to Antiek",
        "text": "Click here: https://...",
        "html": "<p>Click <a href='...'>here</a></p>",
    }
    # from_addr explicitly NOT in the body — AgentMail's inbox is
    # the canonical sender.
    assert "from" not in body


def test_send_omits_html_when_not_provided(monkeypatch):
    p = AgentMailEmailProvider(api_key="am_k", inbox_id="inb_abc")
    with _mock_urlopen(monkeypatch, status_code=200, body={"message_id": "msg_1"}) as captured:
        p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))
    body = json.loads(captured["data"].decode("utf-8"))
    assert "html" not in body
    assert body["text"] == "t"


# ── Response handling ────────────────────────────────────────────────


def test_send_returns_record_with_message_id(monkeypatch):
    p = AgentMailEmailProvider(api_key="am_k", inbox_id="inb_abc")
    with _mock_urlopen(monkeypatch, status_code=200, body={"message_id": "msg_xyz"}):
        rec = p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))
    assert rec.provider == "agentmail"
    assert rec.provider_message_id == "msg_xyz"
    assert rec.email.to == "x@y.com"


def test_send_falls_back_to_id_field(monkeypatch):
    """If AgentMail returns ``id`` instead of ``message_id`` in some
    response shape, we still capture it."""
    p = AgentMailEmailProvider(api_key="am_k", inbox_id="inb_abc")
    with _mock_urlopen(monkeypatch, status_code=200, body={"id": "msg_zzz"}):
        rec = p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))
    assert rec.provider_message_id == "msg_zzz"


# ── Error handling ───────────────────────────────────────────────────


def test_send_surfaces_4xx_error(monkeypatch):
    p = AgentMailEmailProvider(api_key="am_k", inbox_id="inb_abc")
    with _mock_urlopen(monkeypatch, status_code=422, body={"error": {"message": "to invalid"}}):
        with pytest.raises(EmailDeliveryFailure, match="HTTP 422"):
            p.send(OutboundEmail(to="not-email", subject="s", text_body="t"))


def test_send_surfaces_429_rate_limit(monkeypatch):
    """AgentMail returns 429 with Retry-After; we surface the body
    so the caller can see the structured error."""
    p = AgentMailEmailProvider(api_key="am_k", inbox_id="inb_abc")
    with _mock_urlopen(monkeypatch, status_code=429, body={"error": {"message": "rate limited"}}):
        with pytest.raises(EmailDeliveryFailure, match="HTTP 429"):
            p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))


def test_send_surfaces_5xx_error(monkeypatch):
    p = AgentMailEmailProvider(api_key="am_k", inbox_id="inb_abc")
    with _mock_urlopen(monkeypatch, status_code=500, body={"error": {"message": "internal"}}):
        with pytest.raises(EmailDeliveryFailure, match="HTTP 500"):
            p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))


def test_send_handles_transport_error(monkeypatch):
    p = AgentMailEmailProvider(api_key="am_k", inbox_id="inb_abc")

    def boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(EmailDeliveryFailure, match="transport error"):
        p.send(OutboundEmail(to="x@y.com", subject="s", text_body="t"))


# ── Factory test ─────────────────────────────────────────────────────


def test_factory_picks_agentmail(monkeypatch):
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "agentmail")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "am_k")
    monkeypatch.setenv("ANTIEK_AGENTMAIL_INBOX_ID", "inb_abc")
    p = get_email_provider()
    assert isinstance(p, AgentMailEmailProvider)
    assert p.name == "agentmail"


def test_factory_default_still_mock(monkeypatch):
    monkeypatch.delenv("ANTIEK_EMAIL_PROVIDER", raising=False)
    p = get_email_provider()
    assert p.name == "mock"


def test_factory_resend_still_works(monkeypatch):
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "resend")
    p = get_email_provider()
    assert p.name == "resend"
