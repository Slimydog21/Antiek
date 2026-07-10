"""Reproducible weekly comparison of operator, bench, and ND shadow selectors."""

from __future__ import annotations

import hashlib
import html
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from ..suite import SuiteDefinition
from .journal import Journal, LiveCallRecord
from .nd_shadow import NDShadowJournal
from .wedge_config import REQUIRED_TASK_CLASSES, validate_live_suite


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


@dataclass(frozen=True)
class ModelTaskMetrics:
    model_id: str
    task_class: str
    sample_size: int
    expected_samples: int
    complete: bool
    keyword_proxy_quality: float | None
    actual_cost_usd: str
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    success_count: int
    failure_count: int
    timeout_count: int
    availability: float


@dataclass(frozen=True)
class TaskVerdict:
    task_class: str
    bench_winner: str | None
    winner_suppressed_reason: str | None
    operator_driver: str | None
    nd_modal_suggestion: str | None
    nd_sample_size: int
    nd_disagreement_count: int | None
    models: tuple[ModelTaskMetrics, ...]


@dataclass(frozen=True)
class WeeklyVerdict:
    week_id: str
    suite_version: str
    task_verdicts: tuple[TaskVerdict, ...]
    budget_spent_usd: str
    budget_reserved_usd: str
    budget_cap_usd: str
    budget_over_cap: bool
    input_digest: str
    auto_promotion: bool = False
    view_format: str = "html"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _metrics(
    model_id: str,
    task_class: str,
    records: list[LiveCallRecord],
    expected_items: dict[str, str],
) -> ModelTaskMetrics:
    rows = [
        row
        for row in records
        if row.requested_model == model_id and row.task_class == task_class
    ]
    successes = [row for row in rows if row.status == "ok"]
    failures = [row for row in rows if row.status == "failed"]
    timeouts = [row for row in rows if row.status == "timeout"]
    expected = len(expected_items)
    actual_items = {row.item_id: row.prompt_hash for row in rows}
    complete = (
        len(rows) == expected
        and actual_items == expected_items
        and all(row.status == "ok" and row.keyword_score is not None for row in rows)
    )
    quality = None
    if complete:
        quality = round(
            sum(float(row.keyword_score or Decimal("0")) for row in rows) / expected,
            6,
        )
    latencies = [row.latency_ms for row in successes]
    return ModelTaskMetrics(
        model_id=model_id,
        task_class=task_class,
        sample_size=len(rows),
        expected_samples=expected,
        complete=complete,
        keyword_proxy_quality=quality,
        actual_cost_usd=str(sum((row.cost_usd for row in rows), Decimal("0"))),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        success_count=len(successes),
        failure_count=len(failures),
        timeout_count=len(timeouts),
        availability=round(len(successes) / expected, 6),
    )


def build_weekly_verdict(
    *,
    week_id: str,
    wedge_id: str,
    suite: SuiteDefinition,
    call_journal: Journal,
    shadow_journal: NDShadowJournal,
    operator_driver: str | None,
    budget_cap_usd: Decimal,
) -> WeeklyVerdict:
    validate_live_suite(suite)
    if budget_cap_usd <= 0:
        raise ValueError("budget_cap_usd must be positive")
    records = [
        row
        for row in call_journal.replay().values()
        if row.week_id == week_id
        and row.suite_version == suite.suite_version
        and row.wedge_id == wedge_id
    ]
    model_ids = tuple(sorted({row.requested_model for row in records}))
    if len(model_ids) != 2:
        raise ValueError("weekly verdict requires exactly two measured models")
    expected_shadows = {
        (
            "sha256:" + hashlib.sha256(item.item_id.encode()).hexdigest(),
            item.task_class,
            "sha256:" + hashlib.sha256(item.prompt.encode()).hexdigest(),
        )
        for item in suite.items
    }
    shadows = [
        row
        for row in shadow_journal.list_records()
        if row.week_id == week_id
        and row.suite_version == suite.suite_version
        and len(row.candidates) == len(model_ids)
        and set(row.candidates) == set(model_ids)
        and (row.item_id_hash, row.task_class, row.prompt_hash) in expected_shadows
    ]
    charged = sum(
        (
            row.cost_usd
            if row.status == "ok"
            else max(row.reserved_usd, row.cost_usd)
            for row in records
        ),
        Decimal("0"),
    )
    spent = sum((row.cost_usd for row in records), Decimal("0"))
    budget_over_cap = charged > budget_cap_usd
    task_verdicts: list[TaskVerdict] = []
    for task_class in sorted(REQUIRED_TASK_CLASSES):
        expected_items = {
            item.item_id: "sha256:" + hashlib.sha256(item.prompt.encode()).hexdigest()
            for item in suite.items_for(task_class)
        }
        model_metrics = tuple(
            _metrics(model_id, task_class, records, expected_items)
            for model_id in model_ids
        )
        winner: str | None = None
        suppressed: str | None = None
        if budget_over_cap:
            suppressed = "budget_cap_exceeded"
        elif not all(metric.complete for metric in model_metrics):
            suppressed = "incomplete_or_budget_truncated_class"
        else:
            ranked = sorted(
                model_metrics,
                key=lambda metric: metric.keyword_proxy_quality or 0.0,
                reverse=True,
            )
            if ranked[0].keyword_proxy_quality == ranked[1].keyword_proxy_quality:
                suppressed = "quality_tie"
            else:
                winner = ranked[0].model_id
        task_shadows = [
            row
            for row in shadows
            if row.task_class == task_class and row.status == "ok"
        ]
        counts = Counter(row.recommendation for row in task_shadows)
        modal: str | None = None
        if counts:
            top = counts.most_common()
            if len(top) == 1 or top[0][1] > top[1][1]:
                modal = top[0][0]
        disagreement = (
            sum(row.recommendation != winner for row in task_shadows)
            if winner is not None
            else None
        )
        task_verdicts.append(
            TaskVerdict(
                task_class=task_class,
                bench_winner=winner,
                winner_suppressed_reason=suppressed,
                operator_driver=operator_driver,
                nd_modal_suggestion=modal,
                nd_sample_size=len(task_shadows),
                nd_disagreement_count=disagreement,
                models=model_metrics,
            )
        )
    canonical_inputs = json.dumps(
        {
            "calls": [
                row.to_dict()
                for row in sorted(records, key=lambda item: item.call_id)
            ],
            "shadows": [
                row.to_dict()
                for row in sorted(shadows, key=lambda item: item.shadow_id)
            ],
            "suite": suite.suite_version,
            "wedge_id": wedge_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return WeeklyVerdict(
        week_id=week_id,
        suite_version=suite.suite_version,
        task_verdicts=tuple(task_verdicts),
        budget_spent_usd=str(spent),
        budget_reserved_usd=str(charged - spent),
        budget_cap_usd=str(budget_cap_usd),
        budget_over_cap=budget_over_cap,
        input_digest="sha256:" + hashlib.sha256(canonical_inputs.encode()).hexdigest(),
    )


def project_weekly_verdict_html(verdict: WeeklyVerdict) -> str:
    payload = verdict.to_dict()
    rows: list[str] = []
    for task in verdict.task_verdicts:
        for metric in task.models:
            rows.append(
                "<tr>"
                f"<td>{html.escape(task.task_class)}</td>"
                f"<td>{html.escape(metric.model_id)}</td>"
                f"<td>{metric.keyword_proxy_quality if metric.keyword_proxy_quality is not None else 'unmeasured'}</td>"
                f"<td>{html.escape(metric.actual_cost_usd)}</td>"
                f"<td>{metric.p50_latency_ms if metric.p50_latency_ms is not None else 'n/a'} / {metric.p95_latency_ms if metric.p95_latency_ms is not None else 'n/a'}</td>"
                f"<td>{metric.availability:.3f}</td>"
                f"<td>{metric.success_count}/{metric.failure_count}/{metric.timeout_count}</td>"
                f"<td>{metric.sample_size}/{metric.expected_samples}</td>"
                f"<td>{html.escape(task.operator_driver or 'none')}</td>"
                f"<td>{html.escape(task.bench_winner or task.winner_suppressed_reason or 'none')}</td>"
                f"<td>{html.escape(task.nd_modal_suggestion or 'none')} ({task.nd_sample_size})</td>"
                f"<td>{task.nd_disagreement_count if task.nd_disagreement_count is not None else 'n/a'}</td>"
                "</tr>"
            )
    safe_json = json.dumps(payload, sort_keys=True).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Antiek-bench weekly verdict {html.escape(verdict.week_id)}</title>
<style>body{{font:14px/1.45 system-ui;margin:0;color:#202124;background:#fafafa}}main{{max-width:1180px;margin:auto;padding:24px}}h1{{font-size:24px}}table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{border:1px solid #c9c9c9;padding:7px;text-align:left;vertical-align:top}}th{{background:#f1f1ed}}footer{{margin-top:20px;border-top:2px solid #222;padding-top:12px}}</style></head>
<body><main><h1>Antiek-bench weekly verdict</h1>
<p>Week {html.escape(verdict.week_id)} · suite {html.escape(verdict.suite_version)} · budget actual/reserved/cap {html.escape(verdict.budget_spent_usd)} / {html.escape(verdict.budget_reserved_usd)} / {html.escape(verdict.budget_cap_usd)} USD</p>
<table><thead><tr><th>Task</th><th>Model</th><th>Keyword proxy quality</th><th>Cost USD</th><th>p50 / p95 ms</th><th>Availability</th><th>OK / fail / timeout</th><th>Samples</th><th>Operator driver</th><th>Bench winner</th><th>ND shadow modal</th><th>ND disagreements</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<footer>Advisory evidence only. auto_promotion=false. The operator controls model and suite changes. Keyword overlap is a proxy, not judged answer quality.</footer>
<script type="application/json" id="antiek-bench-verdict">{safe_json}</script></main></body></html>"""
