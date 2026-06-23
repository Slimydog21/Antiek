"""NotDiamond orchestrator seam (stub).

Operator vision (2026-06-23):

- **CEO / brain:** Fable or Mythos (tier ``ceo`` in config.yaml — placeholder).
- **Deep researchers:** GLM (TileRT interactive), DeepSeek, Xiaomi, Kimi —
  selected by a NotDiamond-style router for task shape, budget, and latency.

This module does **not** call NotDiamond APIs yet. It returns a structured
plan that upstream loops can translate into ``dispatch(..., latency_mode=)``
and ``provider_override`` / tier overrides without a second dispatcher.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

LatencyMode = Literal["interactive", "autonomous"]
ResearchLane = Literal["glm_tilert", "deepseek", "xiaomi", "kimi", "ceo_future"]


@dataclass(frozen=True)
class OrchestrationPlan:
    """Resolved routing hints for one investigation step."""

    latency_mode: LatencyMode
    primary_lane: ResearchLane
    notes: str


def notdiamond_enabled() -> bool:
    """Kill switch: ``ANTIEK_NOTDIAMOND_DISABLED=1`` → static engagement_policy only."""
    return os.environ.get("ANTIEK_NOTDIAMOND_DISABLED", "").strip() not in (
        "1",
        "true",
        "yes",
    )


def plan_research_lane(
    *,
    user_present: bool,
    deliverable_speed_preference: bool = False,
    task_kind: str = "research",
    brain_choice: str = "glm",
) -> OrchestrationPlan:
    """Heuristic stand-in until NotDiamond is wired.

    Rules:
    - User in product → interactive + ``glm_tilert`` unless they asked for
      speed on a specific deliverable (still interactive; tier stays speed).
    - User off product → autonomous + throughput lane by coarse task kind.

    When ``ANTIEK_NOTDIAMOND_DISABLED`` is set, returns a neutral plan so
    callers rely on ``dispatch_routing_kwargs`` / ``engagement_policy`` only.
    """
    if not notdiamond_enabled():
        mode: LatencyMode = "interactive" if user_present else "autonomous"
        return OrchestrationPlan(
            latency_mode=mode,
            primary_lane="glm_tilert" if user_present else "deepseek",
            notes="NotDiamond disabled — static engagement_policy routing.",
        )
    if user_present or deliverable_speed_preference:
        if brain_choice == "premium":
            return OrchestrationPlan(
                latency_mode="interactive",
                primary_lane="deepseek",
                notes="Premium brain — Opus/pro tiers via engagement_policy base roles.",
            )
        return OrchestrationPlan(
            latency_mode="interactive",
            primary_lane="glm_tilert",
            notes="TileRT GLM-5.2 driving model (engagement_policy.interactive).",
        )
    if task_kind in ("synthesis", "write", "memo"):
        return OrchestrationPlan(
            latency_mode="autonomous",
            primary_lane="kimi",
            notes="Autonomous synthesis → research_synthesis tier (Kimi/OpenRouter).",
        )
    if task_kind in ("bulk", "flash", "ingest"):
        return OrchestrationPlan(
            latency_mode="autonomous",
            primary_lane="xiaomi",
            notes="Autonomous flash → research_flash tier.",
        )
    return OrchestrationPlan(
        latency_mode="autonomous",
        primary_lane="deepseek",
        notes="Autonomous pro reasoning → research_pro tier.",
    )