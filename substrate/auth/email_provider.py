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


def get_email_provider() -> EmailProvider:
    """Resolve the configured provider.

    ``ANTIEK_EMAIL_PROVIDER=resend`` → Resend. Anything else (default)
    → MockEmailProvider. Single decision point keeps the rest of the
    codebase ignorant of which sender is in play.
    """
    choice = os.environ.get("ANTIEK_EMAIL_PROVIDER", "mock").strip().lower()
    if choice == "resend":
        return ResendEmailProvider()
    return MockEmailProvider()
