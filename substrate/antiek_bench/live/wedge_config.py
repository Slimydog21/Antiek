"""Validated configuration for the two-model live Antiek-bench wedge."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from substrate.dispatch.router import DispatchConfig, TierConfig, TierPricing
from substrate.model_registration.registry import ModelEntry

from ..suite import SuiteDefinition

REQUIRED_TASK_CLASSES = frozenset({"distill", "synthesize", "wrestle", "book_qa"})
BENCH_ROLE = "synthesizer"


@dataclass(frozen=True)
class LiveWedgeConfig:
    week_id: str
    candidates: tuple[ModelEntry, ModelEntry]
    cap_usd: Decimal
    timeout_s: float
    max_output_tokens: int
    chars_per_input_token: int = 4

    def __post_init__(self) -> None:
        if not self.week_id.strip():
            raise ValueError("week_id is required")
        if len(self.candidates) != 2:
            raise ValueError("live wedge requires exactly two candidates")
        if self.candidates[0].model_id == self.candidates[1].model_id:
            raise ValueError("live wedge candidates must be distinct")
        for candidate in self.candidates:
            if not candidate.enabled:
                raise ValueError(f"candidate {candidate.model_id} is disabled")
            if not candidate.provider_id.strip():
                raise ValueError(f"candidate {candidate.model_id} has no provider")
            if candidate.input_usd_per_1m <= 0 or candidate.output_usd_per_1m <= 0:
                raise ValueError(
                    f"candidate {candidate.model_id} requires verified positive pricing"
                )
        if self.cap_usd <= 0:
            raise ValueError("cap_usd must be positive")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.chars_per_input_token <= 0:
            raise ValueError("chars_per_input_token must be positive")

    def maximum_cost(self, candidate: ModelEntry, prompt: str) -> Decimal:
        """Conservative call reservation from verified prices and token bounds."""
        input_tokens = max(
            1,
            (len(prompt) + self.chars_per_input_token - 1)
            // self.chars_per_input_token,
        )
        input_cost = Decimal(input_tokens) * Decimal(
            str(candidate.input_usd_per_1m)
        ) / Decimal(1_000_000)
        output_cost = Decimal(self.max_output_tokens) * Decimal(
            str(candidate.output_usd_per_1m)
        ) / Decimal(1_000_000)
        return input_cost + output_cost

    def dispatch_config(self, candidate: ModelEntry) -> DispatchConfig:
        """Create one isolated tier; fallback contamination is impossible."""
        tier = TierConfig(
            name="antiek_bench_live",
            provider=candidate.provider_id,
            model=candidate.model_id,
            max_tokens=self.max_output_tokens,
            temperature=0.2,
            context_budget_tokens=32_000,
            pricing=TierPricing(
                input_per_mtok=candidate.input_usd_per_1m,
                output_per_mtok=candidate.output_usd_per_1m,
            ),
            fallback=None,
        )
        return DispatchConfig(
            role_tiers={BENCH_ROLE: tier.name},
            tiers={tier.name: tier},
        )


def validate_live_suite(suite: SuiteDefinition) -> None:
    present = {item.task_class for item in suite.items}
    missing = REQUIRED_TASK_CLASSES - present
    if missing:
        raise ValueError(f"live suite missing task classes: {sorted(missing)}")
    for item in suite.items:
        if not item.prompt.strip():
            raise ValueError(f"suite item {item.item_id} has an empty prompt")
        if not item.expected_keywords:
            raise ValueError(f"suite item {item.item_id} has no scoring expectations")

