"""Engagement vs autonomous latency policy for dispatch.

Antiek product philosophy (operator 2026-06-23):

- **Interactive** — user is present in the product; optimize TPOT via TileRT
  GLM-5.2 (tier ``speed`` / provider ``tilert``). Replaces Opus/Hermes as
  the *driving* model for engaged sessions.
- **Autonomous** — user off-product; agents optimize **throughput** via API
  researchers (DeepSeek, Xiaomi, Kimi) unless an investigation or deliverable
  carries an explicit speed preference.

This module resolves ``role`` → ``tier_name`` *after* ``config.role_tiers``
and *before* tier lookup in ``router.dispatch``. It does not introduce a
second dispatcher (§16 discipline).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from .brain_choice import (
    DEFAULT_BRAIN_CHOICE,
    DRIVING_ROLES,
    BrainChoice,
    normalize_brain_choice,
)

LatencyMode = Literal["interactive", "autonomous"]


@dataclass(frozen=True)
class EngagementPolicy:
    """Loaded from ``config.yaml`` → ``engagement_policy``."""

    default_mode: LatencyMode
    interactive_overrides: Mapping[str, str]
    autonomous_overrides: Mapping[str, str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> EngagementPolicy:
        if not data:
            return cls(
                default_mode="autonomous",
                interactive_overrides={},
                autonomous_overrides={},
            )
        default_raw = str(data.get("default_mode", "autonomous")).strip().lower()
        default_mode: LatencyMode = (
            "interactive" if default_raw == "interactive" else "autonomous"
        )
        interactive = _read_overrides(data.get("interactive"))
        autonomous = _read_overrides(data.get("autonomous"))
        return cls(
            default_mode=default_mode,
            interactive_overrides=interactive,
            autonomous_overrides=autonomous,
        )


def _read_overrides(block: Any) -> dict[str, str]:
    if not isinstance(block, dict):
        return {}
    raw = block.get("role_tier_overrides")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def resolve_latency_mode(
    explicit: LatencyMode | None,
    *,
    policy: EngagementPolicy | None,
) -> LatencyMode:
    if explicit is not None:
        return explicit
    env = os.environ.get("ANTIEK_LATENCY_MODE", "").strip().lower()
    if env in ("interactive", "autonomous"):
        return env  # type: ignore[return-value]
    if policy is not None:
        return policy.default_mode
    return "autonomous"


def resolve_tier_name(
    role: str,
    base_tier: str,
    *,
    mode: LatencyMode,
    policy: EngagementPolicy | None,
    brain: BrainChoice | None = None,
    deliverable_speed_preference: bool = False,
) -> str:
    """Apply engagement policy overrides on top of ``role_tiers``.

    **Brain toggle:** ``premium`` keeps base tiers while the user is in-product
    (Opus/pro path). ``glm`` applies interactive overrides → TileRT ``speed``.
    **Deliverable speed:** when autonomous but the user asked for speed on a
    specific research/write deliverable, driving roles use interactive overrides.
    """
    if policy is None:
        return base_tier

    effective_brain = brain if brain is not None else DEFAULT_BRAIN_CHOICE
    effective_brain = normalize_brain_choice(effective_brain)

    tier_mode: LatencyMode = mode
    if (
        mode == "autonomous"
        and deliverable_speed_preference
        and effective_brain != "premium"
        and role in DRIVING_ROLES
    ):
        tier_mode = "interactive"

    if tier_mode == "interactive" and effective_brain == "premium":
        return base_tier

    overrides = (
        policy.interactive_overrides
        if tier_mode == "interactive"
        else policy.autonomous_overrides
    )
    return overrides.get(role, base_tier)