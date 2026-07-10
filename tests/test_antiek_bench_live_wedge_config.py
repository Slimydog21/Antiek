from __future__ import annotations

from decimal import Decimal

import pytest

from substrate.antiek_bench.dogfood_fixtures import competitive_dogfood_suite
from substrate.antiek_bench.live import BENCH_ROLE, LiveWedgeConfig, validate_live_suite
from substrate.antiek_bench.suite import SuiteDefinition, SuiteItem
from substrate.model_registration.registry import ModelEntry


def candidate(model: str, provider: str = "provider") -> ModelEntry:
    return ModelEntry(
        model_id=model,
        provider_id=provider,
        enabled=True,
        input_usd_per_1m=1.0,
        output_usd_per_1m=3.0,
    )


def config(*models: ModelEntry) -> LiveWedgeConfig:
    return LiveWedgeConfig(
        week_id="2026-W28",
        candidates=models,  # type: ignore[arg-type]
        cap_usd=Decimal("1.00"),
        timeout_s=30,
        max_output_tokens=1000,
    )


def test_requires_exactly_two_distinct_enabled_priced_models() -> None:
    with pytest.raises(ValueError, match="exactly two"):
        config(candidate("a"))
    with pytest.raises(ValueError, match="distinct"):
        config(candidate("a"), candidate("a"))
    with pytest.raises(ValueError, match="disabled"):
        config(candidate("a"), ModelEntry("b", "p", enabled=False, input_usd_per_1m=1, output_usd_per_1m=1))
    with pytest.raises(ValueError, match="positive pricing"):
        config(candidate("a"), ModelEntry("b", "p", input_usd_per_1m=0, output_usd_per_1m=1))


def test_rejects_nonpositive_operating_bounds() -> None:
    a, b = candidate("a"), candidate("b")
    with pytest.raises(ValueError, match="cap_usd"):
        LiveWedgeConfig("2026-W28", (a, b), Decimal("0"), 1, 1)
    with pytest.raises(ValueError, match="timeout_s"):
        LiveWedgeConfig("2026-W28", (a, b), Decimal("1"), 0, 1)
    with pytest.raises(ValueError, match="max_output_tokens"):
        LiveWedgeConfig("2026-W28", (a, b), Decimal("1"), 1, 0)
    with pytest.raises(ValueError, match="ISO week"):
        LiveWedgeConfig("2026-W99", (a, b), Decimal("1"), 1, 1)


def test_builds_fallback_free_candidate_config_and_conservative_reservation() -> None:
    cfg = config(candidate("a", "provider-a"), candidate("b", "provider-b"))
    dispatch = cfg.dispatch_config(cfg.candidates[0])
    tier = dispatch.tiers[dispatch.role_tiers[BENCH_ROLE]]
    assert tier.provider == "provider-a"
    assert tier.model == "a"
    assert tier.fallback is None
    # 400 input bytes × $1/1M × 1.25 reservation buffer + 1000 output tokens × $3/1M
    assert cfg.maximum_cost(cfg.candidates[0], "x" * 400) == Decimal("0.0035")


def test_live_suite_requires_all_four_classes_and_scoring_expectations() -> None:
    source = competitive_dogfood_suite().items
    live_items = tuple(
        item
        for task_class in ("distill", "synthesize", "wrestle", "book_qa")
        for item in [row for row in source if row.task_class == task_class][:2]
    )
    valid = SuiteDefinition("live-valid", live_items)
    validate_live_suite(valid)
    incomplete = SuiteDefinition(
        suite_version="bad",
        label="bad",
        items=(SuiteItem("one", "distill", "prompt", ("answer",)),),
    )
    with pytest.raises(ValueError, match="missing task classes"):
        validate_live_suite(incomplete)
    empty_expectation = SuiteDefinition(
        suite_version="bad-2",
        label="bad",
        items=valid.items[:-1] + (SuiteItem("empty", "book_qa", "prompt", ()),),
    )
    with pytest.raises(ValueError, match="no scoring expectations"):
        validate_live_suite(empty_expectation)
    duplicate = SuiteDefinition(
        suite_version="duplicate",
        label="bad",
        items=(valid.items[0], valid.items[0], *valid.items[2:]),
    )
    with pytest.raises(ValueError, match="unique"):
        validate_live_suite(duplicate)
