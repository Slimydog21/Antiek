"""Recommended price ceiling math for Midnight Oil jobs.

Formula (explicit, unit-tested):

    recommended_usd =
        duration_minutes
        * TOKENS_PER_MINUTE
        * (input_usd_per_1m + output_usd_per_1m) / 1_000_000
        * fanout_depth
        * SAFETY_FACTOR
        * TIER_MULTIPLIER[research_tier]

Assumptions (documented so they are hard to vary without changing tests):

* ``TOKENS_PER_MINUTE = 4_000`` — combined in+out tokens burned per wall
  minute of active research work at moderate fan-out intensity.
* ``SAFETY_FACTOR = 1.25`` — headroom for retries and tool overhead.
* ``fanout_depth`` defaults to 3 (root + 2 child investigation levels).
* Model rates are USD per 1M tokens (same unit family as settings #440).
* Residual (jl): ``research_tier`` scales intensity — ``fast`` 0.5× (thinking
  off / distill), ``deep`` 1.0× (default), ``wrestle`` 2.0× (long-horizon
  multi-minute competitive depth). Ceiling honesty: depth choice moves the
  recommended price before approve.

This is a **recommendation**, not a charge. The operator must approve a
ceiling before work starts (see ``approve_job``).
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.dispatch.research_tier import normalize_research_tier

TOKENS_PER_MINUTE = 4_000
SAFETY_FACTOR = 1.25
DEFAULT_FANOUT_DEPTH = 3

# Residual (jl): closed research tier → ceiling intensity multiplier.
TIER_MULTIPLIER: dict[str, float] = {
    "fast": 0.5,
    "deep": 1.0,
    "wrestle": 2.0,
}


@dataclass(frozen=True)
class ModelPricing:
    """Per-1M-token rates for ceiling math (pure; no network)."""

    model_id: str
    input_usd_per_1m: float
    output_usd_per_1m: float


# Conservative defaults for offline tests / when settings rates are unknown.
DEFAULT_PRICING: dict[str, ModelPricing] = {
    "default": ModelPricing("default", 1.0, 3.0),
    "glm-5.2": ModelPricing("glm-5.2", 0.5, 1.5),
    "gpt-5.5": ModelPricing("gpt-5.5", 5.0, 15.0),
    "composer-2.5": ModelPricing("composer-2.5", 2.0, 6.0),
    "mimo-v2.5": ModelPricing("mimo-v2.5", 0.8, 2.4),
}


def resolve_pricing(model_id: str | None, pricing: ModelPricing | None = None) -> ModelPricing:
    if pricing is not None:
        return pricing
    key = (model_id or "default").strip() or "default"
    return DEFAULT_PRICING.get(key, DEFAULT_PRICING["default"])


def tier_multiplier(research_tier: str | None = None) -> float:
    """Return closed-set intensity multiplier for a research tier (jl)."""
    tier = normalize_research_tier(research_tier)
    return float(TIER_MULTIPLIER.get(tier, TIER_MULTIPLIER["deep"]))


def recommend_price_ceiling(
    duration_minutes: int,
    *,
    model_id: str | None = None,
    fanout_depth: int = DEFAULT_FANOUT_DEPTH,
    pricing: ModelPricing | None = None,
    research_tier: str | None = None,
) -> float:
    """Return recommended USD ceiling for a Midnight Oil job.

    Raises ``ValueError`` for non-positive duration or fanout_depth.
    Residual (jl): optional ``research_tier`` scales the recommendation.
    """
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    if fanout_depth <= 0:
        raise ValueError("fanout_depth must be positive")

    rates = resolve_pricing(model_id, pricing)
    combined_per_1m = rates.input_usd_per_1m + rates.output_usd_per_1m
    mult = tier_multiplier(research_tier)
    raw = (
        float(duration_minutes)
        * float(TOKENS_PER_MINUTE)
        * combined_per_1m
        / 1_000_000.0
        * float(fanout_depth)
        * float(SAFETY_FACTOR)
        * mult
    )
    # Round to cents for operator-facing ceilings.
    return round(raw, 2)
