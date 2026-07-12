from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest

from substrate.antiek_bench.live import (
    HardBudget,
    Journal,
    LiveCallRecord,
    LiveWedgeConfig,
    ReconciliationRequiredError,
    run_live_wedge,
)
from substrate.antiek_bench.live.live_run import _wedge_id, fake_dispatch_result
from substrate.antiek_bench.store import InMemoryBenchStore
from substrate.antiek_bench.suite import SuiteDefinition, SuiteItem
from substrate.model_registration.registry import ModelEntry


class DirectTimeout:
    def run(self, fn, timeout_s: float):  # type: ignore[no-untyped-def]
        del timeout_s
        return fn()


def suite() -> SuiteDefinition:
    return SuiteDefinition(
        suite_version="live-suite-v1",
        items=(
            SuiteItem("d", "distill", "distill attention", ("attention",)),
            SuiteItem("d2", "distill", "distill memory", ("memory",)),
            SuiteItem("s", "synthesize", "synthesize evidence", ("evidence",)),
            SuiteItem("s2", "synthesize", "synthesize sources", ("sources",)),
            SuiteItem("w", "wrestle", "wrestle tension", ("tension",)),
            SuiteItem("w2", "wrestle", "wrestle tradeoff", ("tradeoff",)),
            SuiteItem("b", "book_qa", "answer book", ("book",)),
            SuiteItem("b2", "book_qa", "answer chapter", ("chapter",)),
        ),
    )


def wedge() -> LiveWedgeConfig:
    return LiveWedgeConfig(
        week_id="2026-W28",
        candidates=(
            ModelEntry("model-a", "provider-a", input_usd_per_1m=1, output_usd_per_1m=1),
            ModelEntry("model-b", "provider-b", input_usd_per_1m=1, output_usd_per_1m=1),
        ),
        cap_usd=Decimal("1"),
        timeout_s=5,
        max_output_tokens=100,
    )


def test_two_model_wedge_is_fallback_free_receipted_and_replayable(tmp_path) -> None:
    calls: list[tuple[str, str]] = []

    def dispatch(prompt, role, *, investigation_id, max_tokens, config):  # type: ignore[no-untyped-def]
        del role, investigation_id, max_tokens
        tier = next(iter(config.tiers.values()))
        assert tier.fallback is None
        assert tier.provider is not None and tier.model is not None
        calls.append((tier.provider, tier.model))
        return fake_dispatch_result(
            text=prompt,
            provider=tier.provider,
            model=tier.model,
            event_id=f"evt-{len(calls)}",
            cost_usd=0.00001,
        )

    store = InMemoryBenchStore()
    journal = Journal(tmp_path / "live.jsonl")
    first = run_live_wedge(
        config=wedge(),
        suite=suite(),
        store=store,
        journal=journal,
        timeout_runner=DirectTimeout(),
        dispatch_fn=dispatch,
        live_enabled=True,
    )
    assert len(calls) == 16
    assert {row for row in calls} == {
        ("provider-a", "model-a"),
        ("provider-b", "model-b"),
    }
    assert all(run.mean_score == 1 for run in first)
    assert len(journal.replay()) == 16
    assert all(
        row.route_receipt_id.startswith("receipt_sha256:") for row in journal.replay().values()
    )
    assert all(row.status == "ok" for row in journal.replay().values())
    assert all(run.get("mock_run") is False for run in store.list_runs())
    assert all(run["measurement"]["completed_count"] == 8 for run in store.list_runs())
    assert all(len(run["measurement"]["route_receipt_ids"]) == 8 for run in store.list_runs())

    replay = run_live_wedge(
        config=wedge(),
        suite=suite(),
        store=store,
        journal=journal,
        timeout_runner=DirectTimeout(),
        dispatch_fn=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("replay must not dispatch")
        ),
        live_enabled=True,
    )
    assert replay == first
    assert len(calls) == 16


def test_candidate_failure_scores_zero_without_cross_model_fallback(tmp_path) -> None:
    calls: list[str] = []

    def dispatch(prompt, role, *, investigation_id, max_tokens, config):  # type: ignore[no-untyped-def]
        del prompt, role, investigation_id, max_tokens
        tier = next(iter(config.tiers.values()))
        assert tier.model is not None
        calls.append(tier.model)
        if tier.model == "model-a":
            raise RuntimeError("provider-a unavailable")
        return fake_dispatch_result(
            text="no expected words",
            provider="provider-b",
            model="model-b",
            event_id=f"evt-{len(calls)}",
            cost_usd=0.00001,
        )

    runs = run_live_wedge(
        config=wedge(),
        suite=suite(),
        store=InMemoryBenchStore(),
        journal=Journal(tmp_path / "live.jsonl"),
        timeout_runner=DirectTimeout(),
        dispatch_fn=dispatch,
        live_enabled=True,
    )
    assert runs[0].mean_score == 0
    assert calls[:8] == ["model-a"] * 8
    assert calls[8:] == ["model-b"] * 8


def test_live_wedge_refuses_dispatch_without_explicit_enablement(tmp_path) -> None:
    called = False

    def dispatch(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        raise AssertionError("must not dispatch")

    try:
        run_live_wedge(
            config=wedge(),
            suite=suite(),
            store=InMemoryBenchStore(),
            journal=Journal(tmp_path / "live.jsonl"),
            timeout_runner=DirectTimeout(),
            dispatch_fn=dispatch,
        )
    except PermissionError as exc:
        assert "operator" in str(exc)
    else:
        raise AssertionError("expected explicit live gate")
    assert called is False


def test_timeouts_are_zero_scored_and_separately_measured(tmp_path) -> None:
    class AlwaysTimeout:
        def run(self, fn, timeout_s: float):  # type: ignore[no-untyped-def]
            del fn, timeout_s
            raise TimeoutError

    store = InMemoryBenchStore()
    runs = run_live_wedge(
        config=wedge(),
        suite=suite(),
        store=store,
        journal=Journal(tmp_path / "live.jsonl"),
        timeout_runner=AlwaysTimeout(),
        dispatch_fn=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("timeout harness must not invoke dispatch")
        ),
        live_enabled=True,
    )
    assert all(run.mean_score == 0 for run in runs)
    assert all(run["measurement"]["timeout_count"] == 8 for run in store.list_runs())
    assert all(run["measurement"]["failure_count"] == 0 for run in store.list_runs())


def test_cap_exhaustion_is_explicit_zero_charge_evidence(tmp_path) -> None:
    base = wedge()
    too_small = LiveWedgeConfig(
        week_id=base.week_id,
        candidates=base.candidates,
        cap_usd=Decimal("0.000001"),
        timeout_s=base.timeout_s,
        max_output_tokens=base.max_output_tokens,
    )
    called = False

    def dispatch(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        raise AssertionError("must not dispatch")

    store = InMemoryBenchStore()
    journal = Journal(tmp_path / "live.jsonl")
    runs = run_live_wedge(
        config=too_small,
        suite=suite(),
        store=store,
        journal=journal,
        timeout_runner=DirectTimeout(),
        dispatch_fn=dispatch,
        live_enabled=True,
    )
    assert called is False
    assert all(run.mean_score == 0 for run in runs)
    assert all(row.status == "skipped_budget" for row in journal.replay().values())
    assert HardBudget(too_small.cap_usd, journal).total_charged == 0
    assert all(run["measurement"]["budget_skipped_count"] == 8 for run in store.list_runs())


def test_maximum_cost_covers_cache_creation_premium() -> None:
    config = wedge()
    candidate = config.candidates[0]
    prompt = "four"
    expected = (
        Decimal(len(prompt.encode())) * Decimal("1.25") * Decimal(str(candidate.input_usd_per_1m))
        + Decimal(config.max_output_tokens) * Decimal(str(candidate.output_usd_per_1m))
    ) / Decimal(1_000_000)
    assert config.maximum_cost(candidate, prompt) == expected


def test_wedge_identity_changes_with_pricing_and_timeout() -> None:
    base = wedge()
    current_suite = suite()
    first, second = base.candidates
    repriced = LiveWedgeConfig(
        week_id=base.week_id,
        candidates=(
            ModelEntry(
                first.model_id,
                first.provider_id,
                input_usd_per_1m=2,
                output_usd_per_1m=first.output_usd_per_1m,
            ),
            second,
        ),
        cap_usd=base.cap_usd,
        timeout_s=base.timeout_s,
        max_output_tokens=base.max_output_tokens,
    )
    retimed = LiveWedgeConfig(
        week_id=base.week_id,
        candidates=base.candidates,
        cap_usd=base.cap_usd,
        timeout_s=base.timeout_s + 1,
        max_output_tokens=base.max_output_tokens,
    )
    assert _wedge_id(base, current_suite) != _wedge_id(repriced, current_suite)
    assert _wedge_id(base, current_suite) != _wedge_id(retimed, current_suite)


@pytest.mark.parametrize(
    ("cap", "timeout", "input_price"),
    [
        (Decimal("Infinity"), 5.0, 1.0),
        (Decimal("1"), float("nan"), 1.0),
        (Decimal("1"), 5.0, float("nan")),
    ],
)
def test_wedge_rejects_non_finite_values(cap, timeout, input_price) -> None:  # type: ignore[no-untyped-def]
    base = wedge()
    first, second = base.candidates
    first = ModelEntry(
        first.model_id,
        first.provider_id,
        input_usd_per_1m=input_price,
        output_usd_per_1m=first.output_usd_per_1m,
    )
    with pytest.raises(ValueError):
        LiveWedgeConfig(
            week_id=base.week_id,
            candidates=(first, second),
            cap_usd=cap,
            timeout_s=timeout,
            max_output_tokens=base.max_output_tokens,
        )


def test_unsettled_reservation_requires_reconciliation(tmp_path) -> None:
    config = wedge()
    current_suite = suite()
    first_candidate = config.candidates[0]
    first_item = current_suite.items[0]
    journal = Journal(tmp_path / "live.jsonl")
    journal.append(
        LiveCallRecord(
            wedge_id=_wedge_id(config, current_suite),
            week_id=config.week_id,
            suite_version=current_suite.suite_version,
            requested_provider=first_candidate.provider_id,
            requested_model=first_candidate.model_id,
            task_class=first_item.task_class,
            item_id=first_item.item_id,
            status="reserved",
            reserved_usd=config.maximum_cost(first_candidate, first_item.prompt),
            prompt_hash="sha256:" + hashlib.sha256(first_item.prompt.encode()).hexdigest(),
        )
    )
    with pytest.raises(ReconciliationRequiredError):
        run_live_wedge(
            config=config,
            suite=current_suite,
            store=InMemoryBenchStore(),
            journal=journal,
            timeout_runner=DirectTimeout(),
            dispatch_fn=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("reconciliation must not redispatch")
            ),
            live_enabled=True,
        )
