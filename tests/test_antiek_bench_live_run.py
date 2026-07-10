from __future__ import annotations

from decimal import Decimal

import pytest

from substrate.antiek_bench.live import Journal, LiveWedgeConfig, run_live_wedge
from substrate.antiek_bench.live.live_run import fake_dispatch_result
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
    assert all(row.route_receipt_id.startswith("evt-") for row in journal.replay().values())
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


def test_cap_exhaustion_fails_before_dispatch(tmp_path) -> None:
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

    with pytest.raises(ValueError, match="budget exceeded"):
        run_live_wedge(
            config=too_small,
            suite=suite(),
            store=InMemoryBenchStore(),
            journal=Journal(tmp_path / "live.jsonl"),
            timeout_runner=DirectTimeout(),
            dispatch_fn=dispatch,
            live_enabled=True,
        )
    assert called is False
