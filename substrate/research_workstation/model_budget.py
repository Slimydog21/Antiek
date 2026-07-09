"""Model-driver budget bar + proposed-prompt cost projection.

Operator vision: decision-tree model selection shows how much of the
API-key budget has been used, and projects whether the *proposed* prompt
would exceed the limit before send.

Pure arithmetic. Does not read API keys, call providers, or persist usage.
The settings surface wires real usage counters into ``BudgetLimit.used_usd``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .midnight_oil import DEFAULT_RATE_CARD, ModelRateCard


class BudgetError(ValueError):
    """Invalid budget or projection inputs."""


@dataclass(frozen=True)
class BudgetLimit:
    """Operator-configured budget for one API key / model pool."""

    limit_usd: float
    used_usd: float
    label: str = "default"

    def __post_init__(self) -> None:
        if self.limit_usd < 0:
            raise BudgetError("limit_usd must be non-negative")
        if self.used_usd < 0:
            raise BudgetError("used_usd must be non-negative")


@dataclass(frozen=True)
class CostProjection:
    """Projected cost of a proposed prompt (+ expected completion)."""

    prompt_chars: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    projected_cost_usd: float
    model_id: str
    chars_per_token: float


@dataclass(frozen=True)
class UsageBar:
    """UI-ready usage bar state for the decision-tree / settings surface."""

    label: str
    limit_usd: float
    used_usd: float
    remaining_usd: float
    fraction_used: float  # 0.0 .. 1.0+ (can exceed if already over)
    percent_used: float
    projected_cost_usd: float | None
    projected_used_usd: float | None
    projected_fraction: float | None
    would_exceed: bool
    over_budget_usd: float


# OpenAI-ish heuristic; overridable for non-English / code-heavy prompts.
DEFAULT_CHARS_PER_TOKEN = 4.0


def estimate_tokens(text: str, *, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
    """Estimate token count from character length (no tokenizer dependency)."""
    if chars_per_token <= 0:
        raise BudgetError("chars_per_token must be > 0")
    n = len(text)
    if n == 0:
        return 0
    return max(1, int(math.ceil(n / chars_per_token)))


def project_prompt_cost(
    prompt: str,
    *,
    expected_output_tokens: int = 1024,
    rate_card: ModelRateCard = DEFAULT_RATE_CARD,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
) -> CostProjection:
    """Project USD cost of sending ``prompt`` with ``expected_output_tokens``.

    Input tokens estimated from prompt length; output tokens are caller-
    supplied (the decision tree can use role-specific defaults).
    """
    if expected_output_tokens < 0:
        raise BudgetError("expected_output_tokens must be non-negative")
    input_tokens = estimate_tokens(prompt, chars_per_token=chars_per_token)
    out_tokens = int(expected_output_tokens)
    cost = (
        (input_tokens / 1000.0) * rate_card.usd_per_1k_input
        + (out_tokens / 1000.0) * rate_card.usd_per_1k_output
    )
    return CostProjection(
        prompt_chars=len(prompt),
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=out_tokens,
        projected_cost_usd=round(cost, 6),
        model_id=rate_card.model_id,
        chars_per_token=chars_per_token,
    )


def would_exceed_budget(
    limit: BudgetLimit,
    projection: CostProjection,
) -> bool:
    """True if used + projected cost would exceed the operator limit."""
    if limit.limit_usd == 0:
        # Zero limit means no spend allowed — any positive projection exceeds.
        return projection.projected_cost_usd > 0 or limit.used_usd > 0
    return (limit.used_usd + projection.projected_cost_usd) > limit.limit_usd


def usage_bar(
    limit: BudgetLimit,
    projection: CostProjection | None = None,
) -> UsageBar:
    """Build the usage-bar state for settings / decision-tree tab.

    When ``projection`` is provided, also fills projected fields so the UI
    can show "if I send this prompt, budget goes from X% → Y%."
    """
    remaining = limit.limit_usd - limit.used_usd
    if limit.limit_usd > 0:
        fraction = limit.used_usd / limit.limit_usd
    else:
        fraction = 1.0 if limit.used_usd > 0 else 0.0

    proj_cost: float | None = None
    proj_used: float | None = None
    proj_frac: float | None = None
    exceeds = False
    over = 0.0

    if projection is not None:
        proj_cost = projection.projected_cost_usd
        proj_used = limit.used_usd + projection.projected_cost_usd
        if limit.limit_usd > 0:
            proj_frac = proj_used / limit.limit_usd
        else:
            proj_frac = 1.0 if proj_used > 0 else 0.0
        exceeds = would_exceed_budget(limit, projection)
        if exceeds:
            over = max(0.0, proj_used - limit.limit_usd)
    else:
        if limit.limit_usd > 0 and limit.used_usd > limit.limit_usd:
            exceeds = True
            over = limit.used_usd - limit.limit_usd
        elif limit.limit_usd == 0 and limit.used_usd > 0:
            exceeds = True
            over = limit.used_usd

    return UsageBar(
        label=limit.label,
        limit_usd=limit.limit_usd,
        used_usd=limit.used_usd,
        remaining_usd=remaining,
        fraction_used=fraction,
        percent_used=round(fraction * 100.0, 2),
        projected_cost_usd=proj_cost,
        projected_used_usd=round(proj_used, 6) if proj_used is not None else None,
        projected_fraction=proj_frac,
        would_exceed=exceeds,
        over_budget_usd=round(over, 6),
    )
