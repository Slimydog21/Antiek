"""Midnight oil — timed autonomous research swarm costing (dry-run).

Operator vision: user sets a work duration + goals; the system recommends a
price ceiling for approval; agents execute without the user living in the
workstation. This module owns the **plan + recommended ceiling** pure logic.

Live swarm spend, provider dispatch, and operator approval plumbing are
out of scope here (criterion: no pretend live swarm success). Caps compose
with existing ``orchestration.continuous.budget`` per-investigation defaults
but do not import that module (keep pure + unit-testable).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


class MidnightOilError(ValueError):
    """Invalid midnight-oil plan inputs."""


@dataclass(frozen=True)
class ModelRateCard:
    """Cost + throughput assumptions for ceiling math.

    Rates are USD per 1K tokens. ``tokens_per_minute`` is a conservative
    end-to-end estimate (prompt + completion + tool overhead), not raw
    model decode speed — ceilings must not be optimistically low.
    """

    model_id: str
    usd_per_1k_input: float
    usd_per_1k_output: float
    tokens_per_minute: float
    # Share of tokens that are output (completion). Rest treated as input.
    output_token_share: float = 0.35

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise MidnightOilError("model_id must be non-empty")
        if self.usd_per_1k_input < 0 or self.usd_per_1k_output < 0:
            raise MidnightOilError("rates must be non-negative")
        if self.tokens_per_minute <= 0:
            raise MidnightOilError("tokens_per_minute must be > 0")
        share = float(self.output_token_share)
        if share < 0.0 or share > 1.0:
            raise MidnightOilError("output_token_share must be in [0,1]")
        object.__setattr__(self, "output_token_share", share)


# Conservative default aligned with mid-tier research models (not a live quote).
DEFAULT_RATE_CARD = ModelRateCard(
    model_id="research-default",
    usd_per_1k_input=0.50,
    usd_per_1k_output=1.50,
    tokens_per_minute=4_000.0,
    output_token_share=0.35,
)

# Compose with orchestration continuous budget defaults (documented, not imported).
PER_INVESTIGATION_REFERENCE_CAP_USD = 2.0
DEFAULT_CONTINGENCY = 0.25
MIN_WORK_MINUTES = 5
MAX_WORK_MINUTES = 12 * 60  # 12h hard ceiling on a single midnight-oil session
MAX_AGENTS = 16
MAX_GOALS = 32


@dataclass(frozen=True)
class PriceCeilingRecommendation:
    """Recommended spend ceiling for operator approval."""

    recommended_ceiling_usd: float
    expected_spend_usd: float
    contingency_usd: float
    estimated_tokens: int
    work_minutes: int
    agent_count: int
    goal_count: int
    model_id: str
    per_investigation_cap_usd: float
    notes: tuple[str, ...]


@dataclass(frozen=True)
class MidnightOilPlan:
    """Full dry-run plan the UI / approval gate can present."""

    goals: tuple[str, ...]
    work_minutes: int
    agent_count: int
    rate_card: ModelRateCard
    ceiling: PriceCeilingRecommendation
    requires_operator_approval: bool = True


def _normalize_goals(goals: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for g in goals:
        text = " ".join(str(g).split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= MAX_GOALS:
            break
    if not out:
        raise MidnightOilError("at least one non-empty goal is required")
    return tuple(out)


def recommend_price_ceiling(
    goals: Sequence[str],
    work_minutes: int,
    rate_card: ModelRateCard = DEFAULT_RATE_CARD,
    *,
    agent_count: int = 1,
    contingency: float = DEFAULT_CONTINGENCY,
    per_investigation_cap_usd: float = PER_INVESTIGATION_REFERENCE_CAP_USD,
) -> PriceCeilingRecommendation:
    """Recommend a price ceiling for a midnight-oil session.

    Math (deliberately conservative):
      tokens ≈ work_minutes × tokens_per_minute × agent_count
                × goal_scale (1 + 0.15 × (n_goals - 1), capped at 2.0)
      cost   = input_tokens × in_rate + output_tokens × out_rate
      ceiling = expected × (1 + contingency), then at least
                min(per_investigation_cap × agent_count, expected×1.1)

    Contingency defaults to 25%. Never returns a zero ceiling when work>0.
    """
    clean_goals = _normalize_goals(goals)
    minutes = int(work_minutes)
    if minutes < MIN_WORK_MINUTES:
        raise MidnightOilError(
            f"work_minutes must be >= {MIN_WORK_MINUTES}, got {minutes}"
        )
    if minutes > MAX_WORK_MINUTES:
        raise MidnightOilError(
            f"work_minutes must be <= {MAX_WORK_MINUTES}, got {minutes}"
        )
    agents = int(agent_count)
    if agents < 1 or agents > MAX_AGENTS:
        raise MidnightOilError(
            f"agent_count must be in [1,{MAX_AGENTS}], got {agents}"
        )
    cont = float(contingency)
    if cont < 0.0 or cont > 1.0:
        raise MidnightOilError("contingency must be in [0,1]")
    cap = float(per_investigation_cap_usd)
    if cap < 0.0:
        raise MidnightOilError("per_investigation_cap_usd must be non-negative")

    goal_scale = min(2.0, 1.0 + 0.15 * (len(clean_goals) - 1))
    raw_tokens = minutes * rate_card.tokens_per_minute * agents * goal_scale
    estimated_tokens = int(math.ceil(raw_tokens))
    out_share = rate_card.output_token_share
    output_tokens = estimated_tokens * out_share
    input_tokens = estimated_tokens - output_tokens
    expected = (
        (input_tokens / 1000.0) * rate_card.usd_per_1k_input
        + (output_tokens / 1000.0) * rate_card.usd_per_1k_output
    )
    contingency_usd = expected * cont
    recommended = expected + contingency_usd
    # Floor: never recommend below a thin buffer of expected, and never
    # above a soft multiple of per-investigation caps without noting it.
    soft_cap = cap * agents
    notes: list[str] = []
    if recommended < expected * 1.05 and expected > 0:
        recommended = expected * 1.10
        notes.append("raised ceiling to 10% buffer over expected spend")
    if soft_cap > 0 and recommended > soft_cap * 3:
        notes.append(
            f"ceiling exceeds 3× per-investigation reference "
            f"({soft_cap:.2f} USD for {agents} agents) — operator should "
            f"confirm swarm breadth"
        )
    # Round money to cents for human approval UX.
    expected_r = round(expected, 2)
    cont_r = round(contingency_usd, 2)
    rec_r = round(recommended, 2)
    if rec_r <= 0.0 and minutes > 0:
        rec_r = 0.01
        notes.append("minimum non-zero ceiling applied")

    return PriceCeilingRecommendation(
        recommended_ceiling_usd=rec_r,
        expected_spend_usd=expected_r,
        contingency_usd=cont_r,
        estimated_tokens=estimated_tokens,
        work_minutes=minutes,
        agent_count=agents,
        goal_count=len(clean_goals),
        model_id=rate_card.model_id,
        per_investigation_cap_usd=cap,
        notes=tuple(notes),
    )


def build_midnight_oil_plan(
    goals: Sequence[str],
    work_minutes: int,
    rate_card: ModelRateCard = DEFAULT_RATE_CARD,
    *,
    agent_count: int = 1,
    contingency: float = DEFAULT_CONTINGENCY,
) -> MidnightOilPlan:
    """Build a full midnight-oil plan (always requires operator approval)."""
    clean = _normalize_goals(goals)
    ceiling = recommend_price_ceiling(
        clean,
        work_minutes,
        rate_card,
        agent_count=agent_count,
        contingency=contingency,
    )
    return MidnightOilPlan(
        goals=clean,
        work_minutes=int(work_minutes),
        agent_count=int(agent_count),
        rate_card=rate_card,
        ceiling=ceiling,
        requires_operator_approval=True,
    )
