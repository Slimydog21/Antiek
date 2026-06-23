"""User-selectable driving model (Brain) — closed set.

Operator posture (2026-06-23):

- **glm** (default): GLM-5.2 via TileRT when engaged — cost-efficient, fast.
  Additional models may join this set later after operator vibe-check.
- **premium**: Anthropic/Opus-class driving tiers from ``role_tiers`` (quality
  over marginal cost while in-product).
- **ceo** (reserved): Fable/Mythos — not selectable until provider ships.

Does not replace ``research_tier`` {fast, deep} (research-lane APIs). Brain
governs the *driving* roles under ``engagement_policy``, not flash bulk alone.
"""

from __future__ import annotations

import os
from typing import Literal

from ..event_log import trajectory
from ..schemas import ActionType

BrainChoice = Literal["glm", "premium", "ceo"]

BRAIN_CHOICES: tuple[BrainChoice, ...] = ("glm", "premium")
DEFAULT_BRAIN_CHOICE: BrainChoice = "glm"

# Roles that count as the "brain" / driver (not bulk flash irrigation).
DRIVING_ROLES: frozenset[str] = frozenset(
    {
        "decomposer",
        "connector",
        "challenger",
        "user_agent",
        "synthesizer",
        "knowledge_extractor",
    }
)


def normalize_brain_choice(value: object) -> BrainChoice:
    """Coerce inbound values; unknown → default ``glm``."""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("glm", "premium", "ceo"):
            return v  # type: ignore[return-value]
    return DEFAULT_BRAIN_CHOICE


def _start_payload_dict(investigation_id: str) -> dict | None:
    start = ActionType.INVESTIGATION_START_REQUESTED.value
    try:
        rows = trajectory(investigation_id)
    except Exception:  # pragma: no cover — diagnostic only
        return None
    for row in rows:
        if row.get("action_type") != start:
            continue
        payload = row.get("payload")
        if isinstance(payload, dict):
            return payload
        break
    return None


def read_brain_choice_from_trajectory(investigation_id: str) -> BrainChoice | None:
    """Read explicit ``brain_choice`` from investigation start event, if any."""
    payload = _start_payload_dict(investigation_id)
    if not payload:
        return None
    raw = payload.get("brain_choice")
    if raw is None:
        return None
    return normalize_brain_choice(raw)


def read_deliverable_speed_preference(investigation_id: str) -> bool:
    """Whether this investigation asked for speed on research/write deliverables."""
    payload = _start_payload_dict(investigation_id)
    if not payload:
        return False
    return bool(payload.get("deliverable_speed_preference"))


def resolve_brain_choice(
    explicit: BrainChoice | str | None,
    *,
    investigation_id: str | None = None,
) -> BrainChoice:
    """Precedence: explicit arg → investigation start → env → default."""
    if explicit is not None:
        return normalize_brain_choice(explicit)
    if investigation_id:
        recorded = read_brain_choice_from_trajectory(investigation_id)
        if recorded is not None:
            return recorded
    env = os.environ.get("ANTIEK_BRAIN_CHOICE", "").strip().lower()
    if env:
        return normalize_brain_choice(env)
    return DEFAULT_BRAIN_CHOICE