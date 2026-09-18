"""Speak invitee re-ping email — AgentMail/Resend seam (not author mail).

Consent-scoped continuous ping: optionally deliver the SpeakInvite door
URL via get_email_provider() (AgentMail / Resend / Mock).

INVITEE-directed (not author payout mail). Never emails declined invitees.
Credential absence degrades honestly.

Env gate: ANTIEK_SPEAK_REPING_EMAIL must be truthy to attempt a send.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from substrate.auth.email_provider import (
    EmailDeliveryFailure,
    OutboundEmail,
    get_email_provider,
)

_DEFAULT_PUBLIC_BASE = "https://antiek.ai"


def reping_email_enabled() -> bool:
    return os.environ.get("ANTIEK_SPEAK_REPING_EMAIL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def public_invite_url(invite_path: str) -> str:
    base = (
        os.environ.get("ANTIEK_PUBLIC_BASE_URL", "").strip()
        or _DEFAULT_PUBLIC_BASE
    ).rstrip("/")
    path = invite_path if invite_path.startswith("/") else f"/{invite_path}"
    return f"{base}{path}"


@dataclass(frozen=True)
class RepingEmailResult:
    status: str
    to: str | None = None
    provider: str | None = None
    message_id: str | None = None
    detail: str | None = None


def _format_bodies(
    *,
    who: str,
    project_title: str,
    invite_url: str,
    followups_added: int,
    pending_question_count: int,
) -> tuple[str, str, str]:
    subject = f"A few more questions about {project_title}"
    plural = "" if pending_question_count == 1 else "s"
    pending_line = f"{pending_question_count} question{plural} waiting"
    follow_line = f" (+{followups_added} new)" if followups_added else ""
    greeting = ""
    if who and "@" in who:
        greeting = " " + who.split("@", 1)[0]
    text_body = (
        f"Hi{greeting},"
        + chr(10) + chr(10)
        + f"There are {pending_line}{follow_line} for "
        + f'"{project_title}".'
        + chr(10) + chr(10)
        + "Open your private invite door (no account needed):"
        + chr(10)
        + invite_url
        + chr(10) + chr(10)
        + "If you prefer not to continue, you can decline from that page — "
        + "we will not email you again after a decline."
        + chr(10) + chr(10)
        + "— Antiek Speak"
        + chr(10)
    )
    html = (
        "<p>Hi,</p>"
        + f"<p>There are <strong>{pending_line}</strong>{follow_line} for "
        + f"<em>{project_title}</em>.</p>"
        + f'<p><a href="{invite_url}">Open your private invite door</a> '
        + "(no account needed).</p>"
        + "<p>If you prefer not to continue, you can decline from that page — "
        + "we will not email you again after a decline.</p>"
        + "<p>— Antiek Speak</p>"
    )
    return subject, text_body, html


def try_send_reping_email(
    *,
    to: str | None,
    invite_path: str,
    project_title: str,
    followups_added: int,
    pending_question_count: int,
    send_requested: bool,
) -> RepingEmailResult:
    if not send_requested:
        return RepingEmailResult(status="skipped_not_requested")
    if not to or not str(to).strip() or "@" not in str(to):
        return RepingEmailResult(
            status="skipped_no_address",
            detail="invitee has no email on the invite",
        )
    if not invite_path:
        return RepingEmailResult(
            status="skipped_no_invite_path",
            detail="no invite token/path to share",
        )
    if not reping_email_enabled():
        return RepingEmailResult(
            status="skipped_env_gate",
            to=to.strip(),
            detail=(
                "ANTIEK_SPEAK_REPING_EMAIL unset — set to 1 to enable "
                "AgentMail/Resend re-ping delivery"
            ),
        )

    invite_url = public_invite_url(invite_path)
    subject, text_body, html = _format_bodies(
        who=to.strip(),
        project_title=project_title or "this remembrance",
        invite_url=invite_url,
        followups_added=followups_added,
        pending_question_count=pending_question_count,
    )
    outbound = OutboundEmail(
        to=to.strip(),
        subject=subject,
        text_body=text_body,
        html_body=html,
        from_addr="Antiek Speak <noreply@antiek.ai>",
    )
    try:
        provider = get_email_provider()
        record = provider.send(outbound)
    except EmailDeliveryFailure as exc:
        return RepingEmailResult(
            status="degraded_credentials_or_transport",
            to=to.strip(),
            detail=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        return RepingEmailResult(
            status="degraded_unexpected",
            to=to.strip(),
            detail=str(exc),
        )
    return RepingEmailResult(
        status="sent",
        to=to.strip(),
        provider=record.provider,
        message_id=record.provider_message_id,
    )


__all__ = [
    "RepingEmailResult",
    "public_invite_url",
    "reping_email_enabled",
    "try_send_reping_email",
]
