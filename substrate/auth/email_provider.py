"""Email-sender abstraction.

One ``EmailProvider`` protocol; two implementations:

- ``MockEmailProvider`` — logs the outbound payload to stdout and
  records it in-memory. Used in tests and local dev. The login flow
  works against the mock without any external dependency; the magic
  link is printed where the operator can copy it.
- ``ResendEmailProvider`` — production sender via Resend. The
  ``RESEND_API_KEY`` env var activates it. No SDK dep; plain HTTPS
  POST to ``api.resend.com``.

The factory ``get_email_provider()`` chooses based on
``ANTIEK_EMAIL_PROVIDER`` env (``mock`` | ``resend``). Default is
``mock`` so the substrate boots cleanly without an email account
during local dev + CI.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


class EmailDeliveryFailure(Exception):
    """Raised when the underlying provider rejects the send."""


@dataclass(frozen=True)
class OutboundEmail:
    """A single outbound email's payload."""

    to: str
    subject: str
    text_body: str
    html_body: str | None = None
    from_addr: str = "Antiek <noreply@antiek.ai>"


@dataclass(frozen=True)
class EmailRecord:
    """A record of a successfully-handled send."""

    email: OutboundEmail
    provider: str
    provider_message_id: str | None
    sent_at: str  # ISO 8601 UTC


class EmailProvider(Protocol):
    """Contract every provider satisfies."""

    name: str

    def send(self, email: OutboundEmail) -> EmailRecord: ...


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class MockEmailProvider:
    """Test + local-dev provider. Records every send in-memory and
    prints to stdout so the operator can copy a magic link out of the
    server log when running locally without Resend."""

    name: str = "mock"
    log_to_stdout: bool = True
    sent: list[EmailRecord] = field(default_factory=list)

    def send(self, email: OutboundEmail) -> EmailRecord:
        record = EmailRecord(
            email=email,
            provider=self.name,
            provider_message_id=f"mock-{len(self.sent) + 1}",
            sent_at=_utc_iso(),
        )
        self.sent.append(record)
        if self.log_to_stdout:
            print(
                f"\n[MockEmailProvider] to={email.to} "
                f"subject={email.subject!r}\n"
                f"------ BODY ------\n{email.text_body}\n"
                f"------ END  ------\n",
                flush=True,
            )
        return record

    def clear(self) -> None:
        self.sent.clear()


@dataclass
class ResendEmailProvider:
    """Production sender via Resend.

    Uses Resend's REST API directly — no SDK dep. ``api_key`` reads
    ``RESEND_API_KEY`` by default. Raises ``EmailDeliveryFailure`` on
    any non-2xx response so the caller (magic-link route) can return
    a 503 to the client rather than silently dropping mail.
    """

    name: str = "resend"
    api_key: str = ""
    api_url: str = "https://api.resend.com/emails"

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.environ.get("RESEND_API_KEY", "").strip()

    def send(self, email: OutboundEmail) -> EmailRecord:
        if not self.api_key:
            raise EmailDeliveryFailure(
                "RESEND_API_KEY not configured; cannot send via Resend."
            )
        payload = {
            "from": email.from_addr,
            "to": [email.to],
            "subject": email.subject,
            "text": email.text_body,
        }
        if email.html_body:
            payload["html"] = email.html_body
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.api_url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                parsed = json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise EmailDeliveryFailure(
                f"Resend HTTP {exc.code}: {err_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise EmailDeliveryFailure(f"Resend transport error: {exc}") from exc

        return EmailRecord(
            email=email,
            provider=self.name,
            provider_message_id=parsed.get("id"),
            sent_at=_utc_iso(),
        )


@dataclass
class AgentMailEmailProvider:
    """Production sender via AgentMail.

    AgentMail is built around inboxes — each inbox is an email
    identity that can both send and receive. For Antiek the
    recommended posture (per the 2026-05-22 verdict in
    docs/operator_gate_actions.md) is to create one inbox per
    purpose:

    - ``notifications@antiek.ai`` for magic-link auth + publisher
      Kalshi-pattern notifications (§9.10).
    - ``interviews@antiek.ai`` for §11 interview invitations.
    - ``outreach@antiek.ai`` for §9.13 cross-graph ask-an-expert.

    The operator creates the inbox once via ``POST /inboxes`` (see
    ``infrastructure/runbooks/agentmail-setup.md``) and sets
    ``ANTIEK_AGENTMAIL_INBOX_ID`` on the VM. This provider then
    sends through that inbox; inbound replies route to the same
    inbox where the operator's reply-handler (Sprint 19+) reads
    them.

    The ``from_addr`` field on ``OutboundEmail`` is IGNORED for
    AgentMail — the inbox's own address is the canonical sender.
    Other providers (Resend, Mock) honor ``from_addr`` directly.
    """

    name: str = "agentmail"
    api_key: str = ""
    inbox_id: str = ""
    api_base: str = "https://api.agentmail.to"

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.environ.get("AGENTMAIL_API_KEY", "").strip()
        if not self.inbox_id:
            self.inbox_id = os.environ.get("ANTIEK_AGENTMAIL_INBOX_ID", "").strip()

    def send(self, email: OutboundEmail) -> EmailRecord:
        if not self.api_key:
            raise EmailDeliveryFailure(
                "AGENTMAIL_API_KEY not configured; cannot send via AgentMail."
            )
        if not self.inbox_id:
            raise EmailDeliveryFailure(
                "ANTIEK_AGENTMAIL_INBOX_ID not configured. Create an "
                "AgentMail inbox first (see "
                "infrastructure/runbooks/agentmail-setup.md) and set "
                "ANTIEK_AGENTMAIL_INBOX_ID to its id."
            )
        url = f"{self.api_base.rstrip('/')}/inboxes/{self.inbox_id}/messages/send"
        payload: dict = {
            "to": email.to,
            "subject": email.subject,
            "text": email.text_body,
        }
        if email.html_body:
            payload["html"] = email.html_body
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                parsed = json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            # AgentMail returns 429 with Retry-After for rate limits;
            # we surface the body so the caller's error logging can
            # see the structured shape.
            raise EmailDeliveryFailure(
                f"AgentMail HTTP {exc.code}: {err_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise EmailDeliveryFailure(f"AgentMail transport error: {exc}") from exc

        return EmailRecord(
            email=email,
            provider=self.name,
            provider_message_id=parsed.get("message_id") or parsed.get("id"),
            sent_at=_utc_iso(),
        )


def get_email_provider() -> EmailProvider:
    """Resolve the configured provider.

    ``ANTIEK_EMAIL_PROVIDER``:
    - ``agentmail`` (recommended per docs/operator_gate_actions.md) →
      AgentMail. Closes §9.10 + §11 + §9.13 inbound reply loops.
    - ``resend`` → Resend (transactional-only).
    - anything else (default) → MockEmailProvider.

    Single decision point keeps the rest of the codebase ignorant
    of which sender is in play.
    """
    choice = os.environ.get("ANTIEK_EMAIL_PROVIDER", "mock").strip().lower()
    if choice == "agentmail":
        return AgentMailEmailProvider()
    if choice == "resend":
        return ResendEmailProvider()
    return MockEmailProvider()
