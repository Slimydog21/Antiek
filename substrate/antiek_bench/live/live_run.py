"""Fallback-free measured benchmark runner.

Builds one DispatchConfig per candidate model with a single bench tier and
``fallback=None``.  Uses ``LiveCallRunner`` as the sole call/budget/restart
path.  Provider-enforced maximum cost; per-call timeout; deterministic
restart without redispatch.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from substrate.dispatch.router import (
    DispatchConfig,
    DispatchResult,
    TierConfig,
    TierPricing,
    dispatch,
)

from ..run import ProviderFn, bench_run_id, run_suite
from ..store import BenchStore
from ..suite import SuiteDefinition, TaskClass
from .budget import HardBudget
from .call_runner import LiveCallRunner, ProviderResult, TimeoutRunner
from .journal import Journal
from .wedge_config import ModelWedgeCandidate, WedgeConfig


class ReconciliationRequiredError(RuntimeError):
    """A durable reservation has no terminal settlement after a crash."""


# ---------------------------------------------------------------------------
# DispatchConfig construction (fallback-free per model)
# ---------------------------------------------------------------------------


def build_bench_dispatch_config(
    candidate: ModelWedgeCandidate,
    *,
    role: str = "bench",
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> DispatchConfig:
    """Build a single-tier, fallback-free DispatchConfig for one model.

    The tier has ``fallback=None`` — a provider failure produces a hard
    ``ProviderError`` and never silently substitutes another model.
    """
    pricing = TierPricing(
        input_per_mtok=candidate.input_usd_per_1m,
        output_per_mtok=candidate.output_usd_per_1m,
    )
    tier = TierConfig(
        name=f"bench-{candidate.model_id}",
        provider=candidate.provider_id,
        model=candidate.model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        context_budget_tokens=32000,
        pricing=pricing,
        fallback=None,
    )
    return DispatchConfig(
        role_tiers={role: tier.name},
        tiers={tier.name: tier},
    )


# ---------------------------------------------------------------------------
# Live ProviderFn adapter for run_suite
# ---------------------------------------------------------------------------


def make_live_provider_fn(
    runner: LiveCallRunner,
    *,
    candidate: ModelWedgeCandidate,
    wedge_id: str,
    week_id: str,
    suite_version: str,
    dispatch_config: DispatchConfig,
    investigation_id: str,
    timeout_s: float,
    maximum_cost: Decimal,
    task_classes_by_item: Mapping[str, TaskClass],
    expected_keywords_by_item: Mapping[str, tuple[str, ...]],
    role: str = "bench",
) -> ProviderFn:
    """Wrap ``LiveCallRunner.execute`` into the ``ProviderFn`` signature
    that ``run_suite`` expects: ``(prompt, item_id) -> str``.

    Each call gets its own dispatch invocation, budget reservation, and
    journal settlement.  Restart replay is handled by the journal —
    completed calls are returned from ``execute`` without redispatch.
    """
    _runner = runner
    _candidate = candidate
    _config = dispatch_config
    _inv = investigation_id
    _wedge = wedge_id
    _week = week_id
    _suite = suite_version
    _timeout = timeout_s
    _max_cost = maximum_cost
    _role = role
    _task_classes = task_classes_by_item
    _expected = expected_keywords_by_item

    def _fn(prompt: str, item_id: str) -> str:
        prompt_hash = "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()[:12]

        def _provider() -> ProviderResult:
            input_upper_tokens = len(prompt.encode("utf-8"))
            input_upper_cost = (
                Decimal(input_upper_tokens)
                * Decimal(str(_candidate.input_usd_per_1m))
                * Decimal("1.25")
                / Decimal("1000000")
            )
            remaining = _max_cost - input_upper_cost
            if remaining <= 0:
                raise ValueError("prompt alone exceeds the per-call maximum")
            output_max_tokens = int(
                remaining * Decimal("1000000") / Decimal(str(_candidate.output_usd_per_1m))
            )
            if output_max_tokens <= 0:
                raise ValueError("per-call maximum cannot fund one output token")
            tier_limit = next(iter(_config.tiers.values())).max_tokens
            dr: DispatchResult = dispatch(
                prompt=prompt,
                role=_role,
                investigation_id=_inv,
                config=_config,
                max_tokens=min(output_max_tokens, tier_limit),
            )
            if dr.provider != _candidate.provider_id or dr.model != _candidate.model_id:
                raise ValueError("dispatch attribution differs from requested candidate")
            response_lower = dr.text.lower()
            scoring_text = " ".join(
                keyword for keyword in _expected[item_id] if keyword.lower() in response_lower
            )
            return ProviderResult(
                model_id=dr.model,
                prompt_tokens=dr.usage.input_tokens,
                completion_tokens=dr.usage.output_tokens,
                cost_usd=Decimal(str(dr.cost_usd)),
                latency_ms=dr.latency_ms,
                response_text=dr.text,
                provider_id=dr.provider,
                scoring_text=scoring_text,
            )

        record = _runner.execute(
            wedge_id=_wedge,
            week_id=_week,
            suite_version=_suite,
            requested_provider=_candidate.provider_id,
            requested_model=_candidate.model_id,
            task_class=_task_classes[item_id],
            item_id=item_id,
            prompt_hash=prompt_hash,
            provider_fn=_provider,
            timeout_s=_timeout,
            maximum_cost=_max_cost,
        )

        if record.status == "reserved":
            raise ReconciliationRequiredError(
                f"call {record.call_id} has an unresolved durable reservation"
            )
        return record.scoring_text if record.status == "ok" else ""

    return _fn


# ---------------------------------------------------------------------------
# Deterministic wedge_id
# ---------------------------------------------------------------------------


def deterministic_wedge_id(
    week_id: str,
    suite_version: str,
    model_ids: tuple[str, str],
) -> str:
    """Derive a stable wedge identity from the run parameters."""
    material = f"{week_id}:{suite_version}:{':'.join(sorted(model_ids))}"
    return "wedge_" + hashlib.sha256(f"bench-wedge:v1:{material}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# run_all — the main orchestrator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveRunResult:
    """Result of one full wedge run across both models."""

    wedge_id: str
    week_id: str
    results: tuple[tuple[str, dict[str, float]], ...]  # (model_id, by_task_class)
    journal_records: int


def run_all(
    *,
    config: WedgeConfig,
    week_id: str,
    suite: SuiteDefinition,
    store: BenchStore,
    journal: Journal,
    timeout_runner: TimeoutRunner,
    investigation_id: str = "bench-live",
) -> LiveRunResult:
    """Run the measured benchmark for both models.

    Uses ``LiveCallRunner`` as the sole call/budget/restart path.
    Deterministic restart: completed journal rows are replayed, never
    redispatched.
    """
    wedge_id = deterministic_wedge_id(
        week_id,
        suite.suite_version,
        config.model_ids,
    )

    budget = HardBudget(config.max_usd, journal)
    runner = LiveCallRunner(journal, budget, timeout_runner)

    results: list[tuple[str, dict[str, float]]] = []
    task_classes_by_item = {item.item_id: item.task_class for item in suite.items}
    expected_keywords_by_item = {item.item_id: item.expected_keywords for item in suite.items}
    if set(task_classes_by_item.values()) != {
        "distill",
        "synthesize",
        "wrestle",
        "book_qa",
    }:
        raise ValueError("suite must contain all four canonical task classes")
    if any(not keywords for keywords in expected_keywords_by_item.values()):
        raise ValueError("every live suite item requires scoring expectations")
    for candidate in config.candidates:
        stored = store.get_run(bench_run_id(week_id, suite.suite_version, candidate.model_id))
        if stored is not None:
            by_task_class = stored.get("by_task_class")
            if not isinstance(by_task_class, dict):
                raise ValueError("stored benchmark run has invalid task-class scores")
            results.append(
                (
                    candidate.model_id,
                    {str(key): float(value) for key, value in by_task_class.items()},
                )
            )
            continue
        dispatch_cfg = build_bench_dispatch_config(candidate)
        provider_fn = make_live_provider_fn(
            runner=runner,
            candidate=candidate,
            wedge_id=wedge_id,
            week_id=week_id,
            suite_version=suite.suite_version,
            dispatch_config=dispatch_cfg,
            investigation_id=investigation_id,
            timeout_s=config.timeout_s,
            maximum_cost=config.per_call_maximum_usd,
            task_classes_by_item=task_classes_by_item,
            expected_keywords_by_item=expected_keywords_by_item,
        )
        bench_result = run_suite(
            model_id=candidate.model_id,
            week_id=week_id,
            store=store,
            suite=suite,
            provider_fn=provider_fn,
        )
        results.append((candidate.model_id, bench_result.by_task_class))

    replayed = journal.replay()
    return LiveRunResult(
        wedge_id=wedge_id,
        week_id=week_id,
        results=tuple(results),
        journal_records=len(replayed),
    )
