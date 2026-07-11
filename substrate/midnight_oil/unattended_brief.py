"""Midnight Oil unattended work brief — pure validation.

Operator sets a finite work window, goals, and an approved price ceiling
(recommended ceiling comes from ``price_ceiling_recommend`` separately).
This module does **not** dispatch agents, debit budget, or call providers.

Rules (fail closed):
* duration_minutes must be a positive finite int within [1, 24*60]
* goals: 1..32 non-empty strings (control chars rejected)
* approved_ceiling_cents: int, 0 <= n <= MAX_CEILING_CENTS (finite money)
* recommended_ceiling_cents optional advisory; when set must be same domain
* If approved > recommended when recommended provided → note, not auto-reject
  (operator may approve higher; honesty records the over-recommend)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

MAX_DURATION_MINUTES = 24 * 60
MIN_DURATION_MINUTES = 1
MAX_GOALS = 32
MAX_GOAL_LEN = 2000
MAX_CEILING_CENTS = 1_000_000_000  # $10M hard cap; finite money domain


class UnattendedBriefError(ValueError):
    """Fail-closed validation error for unattended briefs."""


@dataclass(frozen=True)
class UnattendedBrief:
    duration_minutes: int
    goals: tuple[str, ...]
    approved_ceiling_cents: int
    recommended_ceiling_cents: int | None
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_minutes": self.duration_minutes,
            "goals": list(self.goals),
            "approved_ceiling_cents": self.approved_ceiling_cents,
            "recommended_ceiling_cents": self.recommended_ceiling_cents,
            "notes": list(self.notes),
            # Explicit: this brief alone does not authorize live spend.
            "live_execution_authorized": False,
            "authority": "operator_brief_only",
        }


def _require_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UnattendedBriefError(f"{field} must be an int (got {type(value).__name__})")
    return value


def _clean_goal(raw: object, *, index: int) -> str:
    if not isinstance(raw, str):
        raise UnattendedBriefError(f"goals[{index}] must be a string")
    text = raw.strip()
    if not text:
        raise UnattendedBriefError(f"goals[{index}] must be non-empty")
    if len(text) > MAX_GOAL_LEN:
        raise UnattendedBriefError(f"goals[{index}] exceeds {MAX_GOAL_LEN} chars")
    if any(ord(c) < 32 for c in text):
        raise UnattendedBriefError(f"goals[{index}] contains control characters")
    return text


def build_unattended_brief(
    *,
    duration_minutes: object,
    goals: Sequence[object],
    approved_ceiling_cents: object,
    recommended_ceiling_cents: object | None = None,
) -> UnattendedBrief:
    """Validate and materialize an unattended Midnight Oil brief."""
    mins = _require_int(duration_minutes, field="duration_minutes")
    if mins < MIN_DURATION_MINUTES or mins > MAX_DURATION_MINUTES:
        raise UnattendedBriefError(
            f"duration_minutes must be in [{MIN_DURATION_MINUTES}, {MAX_DURATION_MINUTES}]"
        )

    if not isinstance(goals, (list, tuple)):
        raise UnattendedBriefError("goals must be a list or tuple")
    if not goals:
        raise UnattendedBriefError("goals must contain at least one goal")
    if len(goals) > MAX_GOALS:
        raise UnattendedBriefError(f"goals exceeds max of {MAX_GOALS}")
    clean_goals = tuple(_clean_goal(g, index=i) for i, g in enumerate(goals))

    approved = _require_int(approved_ceiling_cents, field="approved_ceiling_cents")
    if approved < 0 or approved > MAX_CEILING_CENTS:
        raise UnattendedBriefError(
            f"approved_ceiling_cents must be in [0, {MAX_CEILING_CENTS}]"
        )

    recommended: int | None
    if recommended_ceiling_cents is None:
        recommended = None
    else:
        recommended = _require_int(
            recommended_ceiling_cents, field="recommended_ceiling_cents"
        )
        if recommended < 0 or recommended > MAX_CEILING_CENTS:
            raise UnattendedBriefError(
                f"recommended_ceiling_cents must be in [0, {MAX_CEILING_CENTS}]"
            )

    notes: list[str] = [
        "live_execution_authorized=false — brief only; spend requires separate consent",
    ]
    if recommended is not None and approved > recommended:
        notes.append(
            f"approved_ceiling_cents ({approved}) exceeds recommended ({recommended})"
        )
    if approved == 0:
        notes.append("zero ceiling — swarm must not spend money")

    return UnattendedBrief(
        duration_minutes=mins,
        goals=clean_goals,
        approved_ceiling_cents=approved,
        recommended_ceiling_cents=recommended,
        notes=tuple(notes),
    )


__all__ = [
    "MAX_CEILING_CENTS",
    "MAX_DURATION_MINUTES",
    "MAX_GOALS",
    "UnattendedBrief",
    "UnattendedBriefError",
    "build_unattended_brief",
]
