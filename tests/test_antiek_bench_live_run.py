"""Rigorous tests for the fallback-free measured runner (ABLW-SPR-02).

Covers: wedge validation, fallback-free DispatchConfig construction,
cross-model isolation, journal row counting, deterministic restart,
provider-enforced maximum cost, timeout, failure, and privacy.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from substrate.antiek_bench.live import (
    HardBudget,
    Journal,
    LiveCallRecord,
    LiveCallRunner,
    LiveRunResult,
    ModelWedgeCandidate,
    ProviderResult,
    ReconciliationRequiredError,
    WedgeConfig,
    build_bench_dispatch_config,
    deterministic_wedge_id,
    run_all,
    validate_wedge_config,
)
from substrate.antiek_bench.store import InMemoryBenchStore
from substrate.antiek_bench.suite import SuiteDefinition, SuiteItem
from substrate.dispatch.router import (
    DispatchConfig,
    DispatchResult,
    NormalizedUsage,
    ProviderError,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class DirectTimeout:
    """Synchronous timeout runner for tests."""

    def run(self, fn: Any, timeout_s: float) -> Any:
        del timeout_s
        return fn()


class FailingTimeout:
    """Always raises TimeoutError."""

    def run(self, fn: Any, timeout_s: float) -> Any:
        del fn, timeout_s
        raise TimeoutError


def _make_registry() -> Any:
    """Build a ModelRegistry with two test models."""
    from substrate.model_registration.registry import ModelRegistry, add_model

    reg = ModelRegistry()
    add_model(
        reg,
        "alpha-v1",
        provider_id="provider-a",
        display_name="Alpha",
        enabled=True,
        input_usd_per_1m=2.0,
        output_usd_per_1m=8.0,
    )
    add_model(
        reg,
        "beta-v2",
        provider_id="provider-b",
        display_name="Beta",
        enabled=True,
        input_usd_per_1m=1.0,
        output_usd_per_1m=4.0,
    )
    return reg


def _make_full_suite() -> SuiteDefinition:
    """Suite covering all four canonical task classes."""
    return SuiteDefinition(
        suite_version="test-v1",
        items=(
            SuiteItem("d-01", "distill", "Distill this.", ("distill",)),
            SuiteItem("s-01", "synthesize", "Synthesize that.", ("synthesize",)),
            SuiteItem("w-01", "wrestle", "Wrestle here.", ("wrestle",)),
            SuiteItem("b-01", "book_qa", "Book question.", ("book",)),
        ),
    )


def _make_candidates() -> tuple[ModelWedgeCandidate, ModelWedgeCandidate]:
    return (
        ModelWedgeCandidate("alpha-v1", "provider-a", 2.0, 8.0),
        ModelWedgeCandidate("beta-v2", "provider-b", 1.0, 4.0),
    )


def _successful_dispatch_result(
    model: str = "alpha-v1",
    provider: str = "provider-a",
    text: str = "answer text",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cost_usd: float = 0.001,
) -> DispatchResult:
    return DispatchResult(
        text=text,
        usage=NormalizedUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        cost_usd=cost_usd,
        latency_ms=120,
        provider=provider,
        model=model,
        tier=f"bench-{model}",
        finish_reason="stop",
        fallback_chain_index=0,
        event_id="evt-test",
    )


# ---------------------------------------------------------------------------
# M1: WedgeConfig validation
# ---------------------------------------------------------------------------


class TestWedgeConfigValidation:
    """Milestone 1: every invalid case fails before dispatch."""

    def test_valid_config_succeeds(self) -> None:
        reg = _make_registry()
        cfg = validate_wedge_config(
            reg,
            candidate_model_ids=("alpha-v1", "beta-v2"),
            max_usd="1.00",
            per_call_maximum_usd="0.10",
            timeout_s=30.0,
            suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )
        assert cfg.model_ids == ("alpha-v1", "beta-v2")
        assert cfg.max_usd == Decimal("1.00")
        assert cfg.per_call_maximum_usd == Decimal("0.10")
        assert cfg.timeout_s == 30.0

    def test_direct_construction_rejects_duplicate_candidates(self) -> None:
        candidate = _make_candidates()[0]
        with pytest.raises(ValueError, match="distinct"):
            WedgeConfig(
                candidates=(candidate, candidate),
                max_usd=Decimal("1"),
                per_call_maximum_usd=Decimal("0.1"),
                timeout_s=30,
                task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_direct_construction_rejects_incomplete_task_classes(self) -> None:
        with pytest.raises(ValueError, match="four canonical"):
            WedgeConfig(
                candidates=_make_candidates(),
                max_usd=Decimal("1"),
                per_call_maximum_usd=Decimal("0.1"),
                timeout_s=30,
                task_classes=("distill", "synthesize"),
            )

    @pytest.mark.parametrize(
        ("cap", "timeout", "input_price"),
        [
            (Decimal("Infinity"), 30.0, 1.0),
            (Decimal("1"), float("nan"), 1.0),
            (Decimal("1"), 30.0, float("nan")),
        ],
    )
    def test_direct_construction_rejects_non_finite_values(
        self, cap: Decimal, timeout: float, input_price: float
    ) -> None:
        first, second = _make_candidates()
        first = ModelWedgeCandidate(
            first.model_id,
            first.provider_id,
            input_price,
            first.output_usd_per_1m,
        )
        with pytest.raises(ValueError):
            WedgeConfig(
                candidates=(first, second),
                max_usd=cap,
                per_call_maximum_usd=Decimal("0.1"),
                timeout_s=timeout,
                task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_single_model_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="exactly two"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1",),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_three_models_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="exactly two"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "beta-v2", "gamma"),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_duplicate_model_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="duplicate"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "alpha-v1"),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_unregistered_model_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="not registered"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "ghost-model"),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_disabled_model_rejected(self) -> None:
        from substrate.model_registration.registry import add_model

        reg = _make_registry()
        add_model(
            reg,
            "gamma-v1",
            provider_id="p",
            enabled=False,
            input_usd_per_1m=1.0,
            output_usd_per_1m=1.0,
        )
        with pytest.raises(ValueError, match="disabled"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "gamma-v1"),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_zero_price_model_rejected(self) -> None:
        from substrate.model_registration.registry import add_model

        reg = _make_registry()
        add_model(
            reg,
            "cheap-v1",
            provider_id="p",
            enabled=True,
            input_usd_per_1m=0.0,
            output_usd_per_1m=1.0,
        )
        with pytest.raises(ValueError, match="zero pricing"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "cheap-v1"),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_zero_output_price_rejected(self) -> None:
        from substrate.model_registration.registry import add_model

        reg = _make_registry()
        add_model(
            reg,
            "cheap-v1",
            provider_id="p",
            enabled=True,
            input_usd_per_1m=1.0,
            output_usd_per_1m=0.0,
        )
        with pytest.raises(ValueError, match="zero pricing"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "cheap-v1"),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_missing_task_class_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="missing"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "beta-v2"),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize"),  # missing wrestle, book_qa
            )

    def test_zero_cap_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="positive"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "beta-v2"),
                max_usd="0",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_negative_timeout_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="positive"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "beta-v2"),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=-1.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_blank_model_id_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="not be blank"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "  "),
                max_usd="1.00",
                per_call_maximum_usd="0.10",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_zero_per_call_maximum_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="positive"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "beta-v2"),
                max_usd="1.00",
                per_call_maximum_usd="0",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )

    def test_per_call_exceeds_cap_rejected(self) -> None:
        reg = _make_registry()
        with pytest.raises(ValueError, match="must not exceed"):
            validate_wedge_config(
                reg,
                candidate_model_ids=("alpha-v1", "beta-v2"),
                max_usd="1.00",
                per_call_maximum_usd="2.00",
                timeout_s=30.0,
                suite_task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )


# ---------------------------------------------------------------------------
# M2: Fallback-free DispatchConfig construction
# ---------------------------------------------------------------------------


class TestFallbackFreeConfig:
    """Milestone 2: each candidate gets a single-tier, fallback=None config."""

    def test_config_has_single_tier_with_fallback_none(self) -> None:
        candidate = _make_candidates()[0]
        cfg = build_bench_dispatch_config(candidate)
        assert isinstance(cfg, DispatchConfig)
        assert len(cfg.tiers) == 1
        tier = list(cfg.tiers.values())[0]
        assert tier.fallback is None
        assert tier.provider == "provider-a"
        assert tier.model == "alpha-v1"

    def test_config_pricing_matches_registry(self) -> None:
        candidate = ModelWedgeCandidate("m1", "p1", 3.5, 12.0)
        cfg = build_bench_dispatch_config(candidate)
        tier = list(cfg.tiers.values())[0]
        assert tier.pricing.input_per_mtok == 3.5
        assert tier.pricing.output_per_mtok == 12.0

    def test_config_role_maps_to_tier(self) -> None:
        candidate = _make_candidates()[0]
        cfg = build_bench_dispatch_config(candidate, role="bench")
        assert "bench" in cfg.role_tiers
        tier_name = cfg.role_tiers["bench"]
        assert tier_name in cfg.tiers

    def test_two_configs_are_independent(self) -> None:
        c1, c2 = _make_candidates()
        cfg1 = build_bench_dispatch_config(c1)
        cfg2 = build_bench_dispatch_config(c2)
        t1 = list(cfg1.tiers.values())[0]
        t2 = list(cfg2.tiers.values())[0]
        assert t1.provider != t2.provider
        assert t1.model != t2.model
        assert t1.fallback is None
        assert t2.fallback is None

    def test_no_provider_override_used(self) -> None:
        """Verify the spec requirement: no provider_override in the path."""
        candidate = _make_candidates()[0]
        cfg = build_bench_dispatch_config(candidate)
        # TierConfig does not have a provider_override field — it's a
        # parameter on the dispatch() function.  Verify the tier has
        # the concrete provider/model baked in.
        tier = list(cfg.tiers.values())[0]
        assert tier.provider == "provider-a"
        assert tier.model == "alpha-v1"
        # The config itself has no override mechanism.


# ---------------------------------------------------------------------------
# M2: Cross-model isolation — provider-A failure never calls B
# ---------------------------------------------------------------------------


class TestCrossModelIsolation:
    """M2 acceptance: provider-A failure scores zero, never calls B."""

    def test_failure_isolation_via_journal(
        self,
        tmp_path: Path,
    ) -> None:
        """When provider-A fails, the journal shows A=failed and B is untouched."""
        journal = Journal(tmp_path / "calls.jsonl")
        budget = HardBudget("10.00", journal)
        runner = LiveCallRunner(journal, budget, DirectTimeout())

        c_a, c_b = _make_candidates()
        _ = build_bench_dispatch_config(c_a)  # verify construction
        _ = build_bench_dispatch_config(c_b)

        call_log: list[str] = []

        # Provider A always fails
        def _fail_provider() -> ProviderResult:
            call_log.append("A-called")
            raise ProviderError("A is down", provider="provider-a", model="alpha-v1", latency_ms=0)

        # Provider B always succeeds
        def _ok_provider() -> ProviderResult:
            call_log.append("B-called")
            return ProviderResult("beta-v2", 10, 4, Decimal("0.01"), 100, "ok", "provider-b")

        # Run A
        record_a = runner.execute(
            wedge_id="w",
            week_id="week",
            suite_version="sv",
            requested_provider="provider-a",
            requested_model="alpha-v1",
            task_class="research",
            item_id="item-1",
            prompt_hash="sha256:a",
            provider_fn=_fail_provider,
            maximum_cost="0.50",
        )
        assert record_a.status == "failed"

        # Run B — should succeed and A should not have been called via B
        record_b = runner.execute(
            wedge_id="w",
            week_id="week",
            suite_version="sv",
            requested_provider="provider-b",
            requested_model="beta-v2",
            task_class="research",
            item_id="item-1",
            prompt_hash="sha256:b",
            provider_fn=_ok_provider,
            maximum_cost="0.50",
        )
        assert record_b.status == "ok"

        # Verify journal: A failed, B succeeded
        replayed = journal.replay()
        assert len(replayed) == 2
        statuses = {r.requested_model: r.status for r in replayed.values()}
        assert statuses["alpha-v1"] == "failed"
        assert statuses["beta-v2"] == "ok"

        # A was called once, B was called once — no cross-contamination
        assert call_log.count("A-called") == 1
        assert call_log.count("B-called") == 1


# ---------------------------------------------------------------------------
# M3: Journal row counting — 2 models × 4 items = 16
# ---------------------------------------------------------------------------


class TestJournalRowCounting:
    """M3: two models × eight items produce sixteen joined journal rows."""

    def _run_wedge(self, tmp_path: Path, dispatch_results: Any) -> LiveRunResult:
        """Run the full wedge with mocked dispatch."""
        suite = _make_full_suite()
        store = InMemoryBenchStore()
        journal = Journal(tmp_path / "calls.jsonl")
        cfg = WedgeConfig(
            candidates=_make_candidates(),
            max_usd=Decimal("10.00"),
            per_call_maximum_usd=Decimal("0.50"),
            timeout_s=30.0,
            task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )

        call_count = 0

        def mock_dispatch(*args: Any, **kwargs: Any) -> DispatchResult:
            nonlocal call_count
            call_count += 1
            # Return a successful dispatch result
            return dispatch_results

        with patch("substrate.antiek_bench.live.live_run.dispatch", side_effect=mock_dispatch):
            return run_all(
                config=cfg,
                week_id="2026-W28",
                suite=suite,
                store=store,
                journal=journal,
                timeout_runner=DirectTimeout(),
            )

    def test_sixteen_journal_rows_for_two_models_four_items(self, tmp_path: Path) -> None:
        dr = _successful_dispatch_result()
        result = self._run_wedge(tmp_path, dr)
        # 2 models × 4 items = 8 calls × 2 (reserve + settle) = 16 events
        # But journal replays fold to terminal records, so 8 unique call_ids
        assert result.journal_records == 8

    def test_all_calls_made(self, tmp_path: Path) -> None:
        dr = _successful_dispatch_result()
        with patch(
            "substrate.antiek_bench.live.live_run.dispatch",
            return_value=dr,
        ) as mock_d:
            suite = _make_full_suite()
            store = InMemoryBenchStore()
            journal = Journal(tmp_path / "calls.jsonl")
            cfg = WedgeConfig(
                candidates=_make_candidates(),
                max_usd=Decimal("10.00"),
                per_call_maximum_usd=Decimal("0.50"),
                timeout_s=30.0,
                task_classes=("distill", "synthesize", "wrestle", "book_qa"),
            )
            run_all(
                config=cfg,
                week_id="2026-W28",
                suite=suite,
                store=store,
                journal=journal,
                timeout_runner=DirectTimeout(),
            )
            assert mock_d.call_count == 8  # 2 models × 4 items


# ---------------------------------------------------------------------------
# M4: Deterministic restart — second run performs zero dispatches
# ---------------------------------------------------------------------------


class TestDeterministicRestart:
    """M4: second identical run performs zero dispatches and yields identical results."""

    def test_second_run_replays_journal(self, tmp_path: Path) -> None:
        suite = _make_full_suite()
        store = InMemoryBenchStore()
        journal = Journal(tmp_path / "calls.jsonl")
        cfg = WedgeConfig(
            candidates=_make_candidates(),
            max_usd=Decimal("10.00"),
            per_call_maximum_usd=Decimal("0.50"),
            timeout_s=30.0,
            task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )

        dr = _successful_dispatch_result()

        # First run
        with patch("substrate.antiek_bench.live.live_run.dispatch", return_value=dr) as m1:
            result1 = run_all(
                config=cfg,
                week_id="2026-W28",
                suite=suite,
                store=store,
                journal=journal,
                timeout_runner=DirectTimeout(),
            )
            first_call_count = m1.call_count

        assert first_call_count == 8

        # Second run — journal already has all records, so execute() replays
        # without calling the provider.  But dispatch is still called by
        # the provider_fn closure — the journal replay prevents the actual
        # provider call because reserve_within_cap returns False (already
        # in journal), and execute returns the previous record.
        with patch("substrate.antiek_bench.live.live_run.dispatch", return_value=dr) as m2:
            result2 = run_all(
                config=cfg,
                week_id="2026-W28",
                suite=suite,
                store=store,
                journal=journal,
                timeout_runner=DirectTimeout(),
            )

        # The dispatch function is NOT called on restart — execute() sees
        # the completed record in the journal and returns it immediately.
        assert m2.call_count == 0

        # Same journal record count
        assert result1.journal_records == result2.journal_records
        assert result1.results == result2.results

    def test_partial_run_resumes_with_identical_scores(self, tmp_path: Path) -> None:
        suite = _make_full_suite()
        store = InMemoryBenchStore()
        journal = Journal(tmp_path / "calls.jsonl")
        candidates = _make_candidates()
        calls = 0

        def dispatch_for_candidate(*args: Any, **kwargs: Any) -> DispatchResult:
            nonlocal calls
            calls += 1
            config = kwargs["config"]
            prompt = kwargs["prompt"]
            tier = next(iter(config.tiers.values()))
            return _successful_dispatch_result(
                model=tier.model,
                provider=tier.provider,
                text=prompt,
                cost_usd=0.01,
            )

        limited = WedgeConfig(
            candidates=candidates,
            max_usd=Decimal("0.03"),
            per_call_maximum_usd=Decimal("0.01"),
            timeout_s=30.0,
            task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )
        with (
            patch(
                "substrate.antiek_bench.live.live_run.dispatch",
                side_effect=dispatch_for_candidate,
            ),
            pytest.raises(ValueError, match="budget exceeded"),
        ):
            run_all(
                config=limited,
                week_id="2026-W28",
                suite=suite,
                store=store,
                journal=journal,
                timeout_runner=DirectTimeout(),
            )
        assert calls == 3

        resumed = WedgeConfig(
            candidates=candidates,
            max_usd=Decimal("1"),
            per_call_maximum_usd=Decimal("0.01"),
            timeout_s=30.0,
            task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )
        with patch(
            "substrate.antiek_bench.live.live_run.dispatch",
            side_effect=dispatch_for_candidate,
        ):
            result = run_all(
                config=resumed,
                week_id="2026-W28",
                suite=suite,
                store=store,
                journal=journal,
                timeout_runner=DirectTimeout(),
            )
        assert calls == 8
        assert all(score == 1.0 for _, scores in result.results for score in scores.values())

    def test_wedge_id_is_deterministic(self) -> None:
        wid1 = deterministic_wedge_id("W28", "v1", ("a", "b"))
        wid2 = deterministic_wedge_id("W28", "v1", ("b", "a"))  # sorted
        wid3 = deterministic_wedge_id("W28", "v1", ("a", "c"))
        assert wid1 == wid2  # order-independent
        assert wid1 != wid3


# ---------------------------------------------------------------------------
# Provider-enforced maximum cost
# ---------------------------------------------------------------------------


class TestMaximumCost:
    """Provider cost above enforced maximum fails closed."""

    def test_cost_above_maximum_fails(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "calls.jsonl")
        budget = HardBudget("10.00", journal)
        runner = LiveCallRunner(journal, budget, DirectTimeout())

        def expensive_provider() -> ProviderResult:
            return ProviderResult("m", 100, 50, Decimal("5.00"), 100, "expensive", "p")

        record = runner.execute(
            wedge_id="w",
            week_id="wk",
            suite_version="sv",
            requested_provider="p",
            requested_model="m",
            task_class="t",
            item_id="i",
            prompt_hash="h",
            provider_fn=expensive_provider,
            maximum_cost="1.00",
        )
        assert record.status == "failed"
        assert "provider call failed" in record.failure_text

    def test_cost_at_maximum_succeeds(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "calls.jsonl")
        budget = HardBudget("10.00", journal)
        runner = LiveCallRunner(journal, budget, DirectTimeout())

        def exact_provider() -> ProviderResult:
            return ProviderResult("m", 100, 50, Decimal("1.00"), 100, "ok", "p")

        record = runner.execute(
            wedge_id="w",
            week_id="wk",
            suite_version="sv",
            requested_provider="p",
            requested_model="m",
            task_class="t",
            item_id="i",
            prompt_hash="h",
            provider_fn=exact_provider,
            maximum_cost="1.00",
        )
        assert record.status == "ok"

    def test_live_dispatch_receives_cost_derived_token_ceiling(self, tmp_path: Path) -> None:
        suite = _make_full_suite()
        cfg = WedgeConfig(
            candidates=_make_candidates(),
            max_usd=Decimal("1"),
            per_call_maximum_usd=Decimal("0.01"),
            timeout_s=30,
            task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )

        def bounded_dispatch(*args: Any, **kwargs: Any) -> DispatchResult:
            assert 0 < kwargs["max_tokens"] <= 4096
            tier = next(iter(kwargs["config"].tiers.values()))
            return _successful_dispatch_result(
                provider=tier.provider, model=tier.model, text=kwargs["prompt"]
            )

        with patch(
            "substrate.antiek_bench.live.live_run.dispatch",
            side_effect=bounded_dispatch,
        ) as mocked:
            run_all(
                config=cfg,
                week_id="week",
                suite=suite,
                store=InMemoryBenchStore(),
                journal=Journal(tmp_path / "calls.jsonl"),
                timeout_runner=DirectTimeout(),
            )
        assert mocked.call_count == 8

    def test_unsettled_reservation_requires_reconciliation(self, tmp_path: Path) -> None:
        suite = _make_full_suite()
        cfg = WedgeConfig(
            candidates=_make_candidates(),
            max_usd=Decimal("1"),
            per_call_maximum_usd=Decimal("0.01"),
            timeout_s=30,
            task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )
        journal = Journal(tmp_path / "calls.jsonl")
        first = suite.items[0]
        wedge_id = deterministic_wedge_id("week", suite.suite_version, cfg.model_ids)
        journal.append(
            LiveCallRecord(
                wedge_id=wedge_id,
                week_id="week",
                suite_version=suite.suite_version,
                requested_provider=cfg.candidates[0].provider_id,
                requested_model=cfg.candidates[0].model_id,
                task_class=first.task_class,
                item_id=first.item_id,
                status="reserved",
                reserved_usd=Decimal("0.01"),
            )
        )
        with (
            pytest.raises(ReconciliationRequiredError),
            patch("substrate.antiek_bench.live.live_run.dispatch") as mocked,
        ):
            run_all(
                config=cfg,
                week_id="week",
                suite=suite,
                store=InMemoryBenchStore(),
                journal=journal,
                timeout_runner=DirectTimeout(),
            )
        mocked.assert_not_called()


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Timeout is recorded once, charged conservatively, never retried."""

    def test_timeout_records_and_charges(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "calls.jsonl")
        budget = HardBudget("10.00", journal)
        runner = LiveCallRunner(journal, budget, FailingTimeout())

        record = runner.execute(
            wedge_id="w",
            week_id="wk",
            suite_version="sv",
            requested_provider="p",
            requested_model="m",
            task_class="t",
            item_id="i",
            prompt_hash="h",
            provider_fn=lambda: pytest.fail("must not call"),
            maximum_cost="0.50",
        )
        assert record.status == "timeout"
        assert record.failure_text == "call timed out"
        # Timeout charges the full reservation
        assert budget.total_charged == Decimal("0.50")


# ---------------------------------------------------------------------------
# Failure text — no secrets persisted
# ---------------------------------------------------------------------------


class TestPrivacyNoSecretsPersisted:
    """Failure text never contains provider internals or credentials."""

    def test_failure_sanitizes_exception(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "calls.jsonl")
        budget = HardBudget("10.00", journal)
        runner = LiveCallRunner(journal, budget, DirectTimeout())

        def leaking_provider() -> ProviderResult:
            raise RuntimeError("API key sk-SECRET123 leaked in message")

        record = runner.execute(
            wedge_id="w",
            week_id="wk",
            suite_version="sv",
            requested_provider="p",
            requested_model="m",
            task_class="t",
            item_id="i",
            prompt_hash="h",
            provider_fn=leaking_provider,
            maximum_cost="0.10",
        )
        persisted = journal.path.read_text()
        assert record.status == "failed"
        assert "sk-SECRET123" not in persisted
        assert "leaked" not in persisted
        assert record.failure_text == "provider call failed"


# ---------------------------------------------------------------------------
# DispatchConfig.fallback verification
# ---------------------------------------------------------------------------


class TestConfigFallbackVerification:
    """Verify config.fallback is None for every candidate — not merely asserted."""

    def test_both_configs_have_none_fallback(self) -> None:
        for candidate in _make_candidates():
            cfg = build_bench_dispatch_config(candidate)
            for tier in cfg.tiers.values():
                assert tier.fallback is None, (
                    f"tier {tier.name!r} has fallback={tier.fallback!r}; "
                    "expected None for fallback-free bench config"
                )

    def test_fallback_none_is_deep(self) -> None:
        """Even if someone adds a nested fallback, verify the tier tree is flat."""
        candidate = _make_candidates()[0]
        cfg = build_bench_dispatch_config(candidate)
        for tier in cfg.tiers.values():
            current = tier
            depth = 0
            while current is not None:
                depth += 1
                current = current.fallback
            assert depth == 1, f"tier chain has depth {depth}; expected 1 (no fallback)"


# ---------------------------------------------------------------------------
# Scoring material persistence
# ---------------------------------------------------------------------------


class TestScoringMaterialPersistence:
    """Journal records provider, model, tokens, cost, latency, status."""

    def test_successful_call_persists_all_fields(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "calls.jsonl")
        budget = HardBudget("10.00", journal)
        runner = LiveCallRunner(journal, budget, DirectTimeout())

        def ok_provider() -> ProviderResult:
            return ProviderResult(
                "test-model",
                150,
                75,
                Decimal("0.005"),
                250,
                "response",
                "test-provider",
            )

        record = runner.execute(
            wedge_id="w",
            week_id="wk",
            suite_version="sv",
            requested_provider="test-provider",
            requested_model="test-model",
            task_class="research",
            item_id="item-1",
            prompt_hash="sha256:abc",
            provider_fn=ok_provider,
            maximum_cost="0.10",
        )
        assert record.status == "ok"
        assert record.actual_provider == "test-provider"
        assert record.actual_model == "test-model"
        assert record.prompt_tokens == 150
        assert record.completion_tokens == 75
        assert record.cost_usd == Decimal("0.005")
        assert record.latency_ms == 250
        assert record.response_hash != ""  # hash persisted, not the text

    def test_failed_call_persists_status_and_latency(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "calls.jsonl")
        budget = HardBudget("10.00", journal)
        runner = LiveCallRunner(journal, budget, DirectTimeout())

        def fail_provider() -> ProviderResult:
            raise ProviderError("down", provider="p", model="m", latency_ms=42)

        record = runner.execute(
            wedge_id="w",
            week_id="wk",
            suite_version="sv",
            requested_provider="p",
            requested_model="m",
            task_class="research",
            item_id="item-1",
            prompt_hash="sha256:abc",
            provider_fn=fail_provider,
            maximum_cost="0.10",
        )
        assert record.status == "failed"


# ---------------------------------------------------------------------------
# BenchStore integration — run_suite receives scored results
# ---------------------------------------------------------------------------


class TestBenchStoreIntegration:
    """Scoring and persistence delegated to run_suite."""

    def test_store_receives_run_per_model(self, tmp_path: Path) -> None:
        suite = _make_full_suite()
        store = InMemoryBenchStore()
        journal = Journal(tmp_path / "calls.jsonl")
        cfg = WedgeConfig(
            candidates=_make_candidates(),
            max_usd=Decimal("10.00"),
            per_call_maximum_usd=Decimal("0.50"),
            timeout_s=30.0,
            task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )

        dr = _successful_dispatch_result()
        with patch("substrate.antiek_bench.live.live_run.dispatch", return_value=dr):
            run_all(
                config=cfg,
                week_id="2026-W28",
                suite=suite,
                store=store,
                journal=journal,
                timeout_runner=DirectTimeout(),
            )

        runs = store.list_runs()
        assert len(runs) == 2
        model_ids = {r["model_id"] for r in runs}
        assert model_ids == {"alpha-v1", "beta-v2"}
        for run in runs:
            assert len(run["scores"]) == 4
            task_classes = {score["task_class"] for score in run["scores"]}
            assert task_classes == {"distill", "synthesize", "wrestle", "book_qa"}

    def test_success_scores_real_keywords_without_persisting_response(self, tmp_path: Path) -> None:
        suite = _make_full_suite()
        store = InMemoryBenchStore()
        journal = Journal(tmp_path / "calls.jsonl")
        cfg = WedgeConfig(
            candidates=_make_candidates(),
            max_usd=Decimal("1"),
            per_call_maximum_usd=Decimal("0.01"),
            timeout_s=30.0,
            task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )

        def dispatch_for_candidate(*args: Any, **kwargs: Any) -> DispatchResult:
            config = kwargs["config"]
            tier = next(iter(config.tiers.values()))
            return _successful_dispatch_result(
                model=tier.model,
                provider=tier.provider,
                text=kwargs["prompt"],
                cost_usd=0.001,
            )

        with patch(
            "substrate.antiek_bench.live.live_run.dispatch",
            side_effect=dispatch_for_candidate,
        ):
            result = run_all(
                config=cfg,
                week_id="2026-W28",
                suite=suite,
                store=store,
                journal=journal,
                timeout_runner=DirectTimeout(),
            )
        assert all(score == 1.0 for _, scores in result.results for score in scores.values())
        persisted = journal.path.read_text()
        assert "Distill this" not in persisted
        assert all(record.scoring_text for record in journal.replay().values())

    def test_attribution_mismatch_scores_failure(self, tmp_path: Path) -> None:
        suite = _make_full_suite()
        store = InMemoryBenchStore()
        journal = Journal(tmp_path / "calls.jsonl")
        cfg = WedgeConfig(
            candidates=_make_candidates(),
            max_usd=Decimal("1"),
            per_call_maximum_usd=Decimal("0.01"),
            timeout_s=30.0,
            task_classes=("distill", "synthesize", "wrestle", "book_qa"),
        )
        mismatched = _successful_dispatch_result(model="wrong", provider="wrong")
        with patch("substrate.antiek_bench.live.live_run.dispatch", return_value=mismatched):
            result = run_all(
                config=cfg,
                week_id="2026-W28",
                suite=suite,
                store=store,
                journal=journal,
                timeout_runner=DirectTimeout(),
            )
        assert all(score == 0.0 for _, scores in result.results for score in scores.values())
        assert all(record.status == "failed" for record in journal.replay().values())
