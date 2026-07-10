"""Pure cost projection from declared budgets and caller-supplied prices."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .tiers import TierBudget

MILLION = Decimal(1_000_000)
INPUT_RESERVATION_BUFFER = Decimal("1.25")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class ModelPrice:
    model_id: str
    input_usd_per_1m: Decimal
    output_usd_per_1m: Decimal

    def __post_init__(self) -> None:
        if not self.model_id.strip() or self.input_usd_per_1m < 0 or self.output_usd_per_1m < 0:
            raise ValueError("model id must be non-empty and prices non-negative")


@dataclass(frozen=True)
class CostInterval:
    lower_usd: Decimal
    upper_usd: Decimal


def _combined(price: ModelPrice) -> Decimal:
    # Same conservative input reservation posture as
    # substrate/antiek_bench/live/wedge_config.py::LiveWedgeConfig.maximum_cost.
    return price.input_usd_per_1m * INPUT_RESERVATION_BUFFER + price.output_usd_per_1m


def project_cost(budget: TierBudget, prices: Sequence[ModelPrice]) -> CostInterval:
    """Project half-use/cheapest through full-use/priciest, rounded to cents."""
    if not prices:
        raise ValueError("at least one declared model price is required")
    rates = [_combined(price) for price in prices]
    lower = Decimal(budget.token_budget) * Decimal("0.5") * min(rates) / MILLION
    upper = Decimal(budget.token_budget) * max(rates) / MILLION
    return CostInterval(
        lower_usd=lower.quantize(CENT, rounding=ROUND_HALF_UP),
        upper_usd=upper.quantize(CENT, rounding=ROUND_HALF_UP),
    )
