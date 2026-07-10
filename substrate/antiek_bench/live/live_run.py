"""Fallback-free, restart-idempotent measured Antiek-bench runner."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Protocol

from substrate.dispatch.base import NormalizedUsage
from substrate.dispatch.router import DispatchConfig, DispatchResult

from ..run import BenchRunResult, TaskScore
from ..store import BenchStore
from ..suite import SuiteDefinition, SuiteItem
from .budget import HardBudget
from .call_runner import LiveCallRunner, ProviderResult, TimeoutRunner
from .journal import Journal
from .wedge_config import BENCH_ROLE, LiveWedgeConfig, validate_live_suite


class DispatchFn(Protocol):
    def __call__(
        self,
        prompt: str,
        role: str,
        *,
        investigation_id: str,
        max_tokens: int,
        config: DispatchConfig,
    ) -> DispatchResult: ...


def _score(response: str, expected: tuple[str, ...]) -> tuple[Decimal, tuple[str, ...]]:
    text = response.lower()
    hits = tuple(keyword for keyword in expected if keyword.lower() in text)
    return Decimal(len(hits)) / Decimal(len(expected)), hits


def _wedge_id(config: LiveWedgeConfig, suite: SuiteDefinition) -> str:
    material = json.dumps(
        {
            "week": config.week_id,
            "suite": suite.suite_version,
            "suite_items": [
                [
                    item.item_id,
                    item.task_class,
                    hashlib.sha256(item.prompt.encode()).hexdigest(),
                    list(item.expected_keywords),
                ]
                for item in suite.items
            ],
            "models": [
                [row.provider_id, row.model_id] for row in config.candidates
            ],
            "max_output_tokens": config.max_output_tokens,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "wedge_" + hashlib.sha256(material.encode()).hexdigest()[:20]


def run_live_wedge(
    *,
    config: LiveWedgeConfig,
    suite: SuiteDefinition,
    store: BenchStore,
    journal: Journal,
    timeout_runner: TimeoutRunner,
    dispatch_fn: DispatchFn,
    live_enabled: bool = False,
) -> tuple[BenchRunResult, BenchRunResult]:
    """Run or replay exactly two models without fallback contamination."""
    if not live_enabled:
        raise PermissionError("live Antiek-bench requires explicit operator enablement")
    validate_live_suite(suite)
    wedge_id = _wedge_id(config, suite)
    call_runner = LiveCallRunner(
        journal,
        HardBudget(config.cap_usd, journal),
        timeout_runner,
    )
    runs: list[BenchRunResult] = []
    for candidate in config.candidates:
        dispatch_config = config.dispatch_config(candidate)
        scores: list[TaskScore] = []
        class_scores: dict[str, list[float]] = {}
        for item in suite.items:
            prompt_hash = "sha256:" + hashlib.sha256(item.prompt.encode()).hexdigest()

            def provider(
                current_item: SuiteItem = item,
                current_config: DispatchConfig = dispatch_config,
            ) -> ProviderResult:
                result = dispatch_fn(
                    current_item.prompt,
                    BENCH_ROLE,
                    investigation_id=f"antiek-bench:{wedge_id}",
                    max_tokens=config.max_output_tokens,
                    config=current_config,
                )
                score, hits = _score(result.text, current_item.expected_keywords)
                return ProviderResult(
                    model_id=result.model,
                    prompt_tokens=result.usage.input_tokens,
                    completion_tokens=result.usage.output_tokens,
                    cost_usd=Decimal(str(result.cost_usd)),
                    latency_ms=result.latency_ms,
                    response_text=result.text,
                    provider_id=result.provider,
                    route_receipt_id=result.event_id or "",
                    keyword_score=score,
                    hit_keywords=hits,
                )

            record = call_runner.execute(
                wedge_id=wedge_id,
                week_id=config.week_id,
                suite_version=suite.suite_version,
                requested_provider=candidate.provider_id,
                requested_model=candidate.model_id,
                task_class=item.task_class,
                item_id=item.item_id,
                prompt_hash=prompt_hash,
                provider_fn=provider,
                timeout_s=config.timeout_s,
                maximum_cost=config.maximum_cost(candidate, item.prompt),
            )
            value = float(record.keyword_score or Decimal("0")) if record.status == "ok" else 0.0
            scores.append(
                TaskScore(
                    item_id=item.item_id,
                    task_class=item.task_class,
                    model_id=candidate.model_id,
                    score=round(value, 6),
                    hit_keywords=record.hit_keywords if record.status == "ok" else (),
                    response_preview=f"[{record.status}] {record.response_hash[:20]}",
                )
            )
            class_scores.setdefault(item.task_class, []).append(value)
        by_class = {
            task_class: round(sum(values) / len(values), 6)
            for task_class, values in sorted(class_scores.items())
        }
        mean = round(sum(row.score for row in scores) / len(scores), 6)
        run_id = f"live_{wedge_id}_{candidate.model_id}"
        run = BenchRunResult(
            run_id=run_id,
            week_id=config.week_id,
            suite_version=suite.suite_version,
            model_id=candidate.model_id,
            scores=tuple(scores),
            mean_score=mean,
            by_task_class=by_class,
        )
        payload = run.to_dict()
        measured = [
            row
            for row in journal.replay().values()
            if row.wedge_id == wedge_id and row.requested_model == candidate.model_id
        ]
        completed = [row for row in measured if row.status == "ok"]
        failures = [row for row in measured if row.status == "failed"]
        timeouts = [row for row in measured if row.status == "timeout"]
        payload.update(
            {
                "live": True,
                "mock_run": False,
                "wedge_id": wedge_id,
                "measurement": {
                    "call_count": len(measured),
                    "completed_count": len(completed),
                    "failure_count": len(failures),
                    "timeout_count": len(timeouts),
                    "failure_rate": round(len(failures) / len(measured), 6),
                    "timeout_rate": round(len(timeouts) / len(measured), 6),
                    "actual_cost_usd": str(sum((row.cost_usd for row in measured), Decimal("0"))),
                    "reserved_usd": str(sum((row.reserved_usd for row in measured), Decimal("0"))),
                    "mean_latency_ms": (
                        round(sum(row.latency_ms for row in completed) / len(completed), 3)
                        if completed
                        else None
                    ),
                    "route_receipt_ids": [
                        row.route_receipt_id for row in completed if row.route_receipt_id
                    ],
                },
            }
        )
        store.put_run(run_id, payload)
        runs.append(run)
    return runs[0], runs[1]


def fake_dispatch_result(
    *,
    text: str,
    provider: str,
    model: str,
    event_id: str,
    cost_usd: float = 0.001,
) -> DispatchResult:
    """Typed deterministic fixture helper; never used by the live entrypoint."""
    return DispatchResult(
        text=text,
        usage=NormalizedUsage(input_tokens=10, output_tokens=10),
        cost_usd=cost_usd,
        latency_ms=10,
        provider=provider,
        model=model,
        tier="antiek_bench_live",
        finish_reason="stop",
        fallback_chain_index=0,
        event_id=event_id,
    )
