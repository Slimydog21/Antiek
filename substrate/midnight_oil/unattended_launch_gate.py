"""Unattended Midnight Oil launch gate — pure, fail-closed.

Combines an operator brief (#849) with explicit spend-consent receipt identity
and an operator approval flag into a **dispatch readiness** decision.

This module never:
* dispatches workers
* debits budget / ledger
* calls providers
* invents a consent receipt

Rules:
* ``brief`` must already be a valid unattended brief dict (or re-built via
  ``build_unattended_brief`` inputs)
* ``operator_approved`` must be an explicit bool (strict; missing → error)
* ``consent_receipt_id`` required non-empty when ceiling > 0 to pass
* ``dispatch_ready`` is True only when approved AND (ceiling==0 OR receipt id)
* ``live_execution_authorized`` is **always False** here — live spend still
  requires the keep-partition worker + signed consent claim path
* ``zero_ceiling_dry_run`` notes when ceiling is 0 and dispatch_ready for planning
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil.unattended_brief import (
    UnattendedBrief,
    UnattendedBriefError,
    build_unattended_brief,
)

MAX_RECEIPT_ID_LEN = 128


class LaunchGateError(ValueError):
    """Fail-closed validation for unattended launch gate."""


@dataclass(frozen=True)
class LaunchGateDecision:
    dispatch_ready: bool
    live_execution_authorized: bool
    zero_ceiling_dry_run: bool
    operator_approved: bool
    consent_receipt_id: str | None
    brief: dict[str, Any]
    reasons: tuple[str, ...]
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatch_ready": self.dispatch_ready,
            "live_execution_authorized": False,  # never invent live auth
            "zero_ceiling_dry_run": self.zero_ceiling_dry_run,
            "operator_approved": self.operator_approved,
            "consent_receipt_id": self.consent_receipt_id,
            "brief": dict(self.brief),
            "reasons": list(self.reasons),
            "notes": list(self.notes),
            "authority": "launch_gate_advisory",
        }


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise LaunchGateError(f"{field} must be an explicit boolean (got {type(value).__name__})")
    return value


def _clean_receipt_id(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LaunchGateError("consent_receipt_id must be a string or null")
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_RECEIPT_ID_LEN:
        raise LaunchGateError(f"consent_receipt_id exceeds {MAX_RECEIPT_ID_LEN} chars")
    if any(ord(c) < 32 for c in text):
        raise LaunchGateError("consent_receipt_id contains control characters")
    return text


def _brief_from_input(
    brief: Mapping[str, Any] | UnattendedBrief | None,
    *,
    duration_minutes: object | None = None,
    goals: Sequence[object] | None = None,
    approved_ceiling_cents: object | None = None,
    recommended_ceiling_cents: object | None = None,
) -> dict[str, Any]:
    if isinstance(brief, UnattendedBrief):
        d = brief.to_dict()
    elif isinstance(brief, Mapping):
        # Re-validate through build_unattended_brief — never trust raw booleans
        # for live_execution_authorized from clients.
        try:
            rebuilt = build_unattended_brief(
                duration_minutes=brief.get("duration_minutes"),
                goals=brief.get("goals") or (),
                approved_ceiling_cents=brief.get("approved_ceiling_cents"),
                recommended_ceiling_cents=brief.get("recommended_ceiling_cents"),
            )
        except UnattendedBriefError as e:
            raise LaunchGateError(f"invalid brief: {e}") from e
        d = rebuilt.to_dict()
    elif brief is None:
        if duration_minutes is None or goals is None or approved_ceiling_cents is None:
            raise LaunchGateError(
                "brief or (duration_minutes, goals, approved_ceiling_cents) required"
            )
        try:
            rebuilt = build_unattended_brief(
                duration_minutes=duration_minutes,
                goals=goals,
                approved_ceiling_cents=approved_ceiling_cents,
                recommended_ceiling_cents=recommended_ceiling_cents,
            )
        except UnattendedBriefError as e:
            raise LaunchGateError(f"invalid brief: {e}") from e
        d = rebuilt.to_dict()
    else:
        raise LaunchGateError("brief must be a mapping, UnattendedBrief, or null with fields")

    # Force honesty on embedded brief live flag
    d["live_execution_authorized"] = False
    d["authority"] = "operator_brief_only"
    return d


def evaluate_unattended_launch_gate(
    *,
    operator_approved: object,
    consent_receipt_id: object | None = None,
    brief: Mapping[str, Any] | UnattendedBrief | None = None,
    duration_minutes: object | None = None,
    goals: Sequence[object] | None = None,
    approved_ceiling_cents: object | None = None,
    recommended_ceiling_cents: object | None = None,
) -> LaunchGateDecision:
    """Decide dispatch readiness without authorizing live spend."""
    approved = _require_bool(operator_approved, field="operator_approved")
    receipt = _clean_receipt_id(consent_receipt_id)
    brief_d = _brief_from_input(
        brief,
        duration_minutes=duration_minutes,
        goals=goals,
        approved_ceiling_cents=approved_ceiling_cents,
        recommended_ceiling_cents=recommended_ceiling_cents,
    )
    ceiling = brief_d["approved_ceiling_cents"]
    if not isinstance(ceiling, int):
        raise LaunchGateError("brief.approved_ceiling_cents must be int")

    reasons: list[str] = []
    notes: list[str] = [
        "live_execution_authorized=false — gate does not authorize live spend",
        "authority=launch_gate_advisory",
        "worker/daemon claim path remains separate",
    ]

    if not approved:
        reasons.append("operator_approved=false")
    if ceiling > 0 and receipt is None:
        reasons.append("consent_receipt_id required when approved_ceiling_cents > 0")
    if ceiling == 0:
        notes.append("zero ceiling — dispatch_ready allows dry-run planning only")

    zero_dry = ceiling == 0
    dispatch_ready = approved and (ceiling == 0 or receipt is not None)
    if not dispatch_ready and not reasons:
        reasons.append("dispatch not ready")

    if dispatch_ready:
        notes.append("dispatch_ready=true — still not live_execution_authorized")

    return LaunchGateDecision(
        dispatch_ready=dispatch_ready,
        live_execution_authorized=False,
        zero_ceiling_dry_run=zero_dry and dispatch_ready,
        operator_approved=approved,
        consent_receipt_id=receipt,
        brief=brief_d,
        reasons=tuple(reasons) if not dispatch_ready else (),
        notes=tuple(notes),
        authority="launch_gate_advisory",
    )


__all__ = [
    "LaunchGateDecision",
    "LaunchGateError",
    "evaluate_unattended_launch_gate",
]
