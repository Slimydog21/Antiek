from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

from substrate.antiek_bench.live import (
    Journal,
    LiveCallRecord,
    NDShadowConfig,
    NDShadowJournal,
    NDShadowRecord,
    NDShadowResponse,
    build_weekly_verdict,
    collect_nd_shadow,
    project_weekly_verdict_html,
)
from substrate.antiek_bench.suite import SuiteDefinition, SuiteItem, SuiteRegistry


def suite() -> SuiteDefinition:
    return SuiteDefinition(
        suite_version="live-suite-v1",
        items=tuple(
            SuiteItem(f"{task}-{index}", task, f"private {task} {index}", (task,))
            for task in ("distill", "synthesize", "wrestle", "book_qa")
            for index in range(2)
        ),
    )


def add_call(
    journal: Journal,
    *,
    model: str,
    task: str,
    item: str,
    prompt: str,
    score: str,
    latency: int,
    status: str = "ok",
) -> None:
    base = dict(
        wedge_id="wedge",
        week_id="2026-W28",
        suite_version="live-suite-v1",
        requested_provider=f"provider-{model[-1]}",
        requested_model=model,
        task_class=task,
        item_id=item,
        reserved_usd=Decimal("0.01"),
        prompt_hash="sha256:" + hashlib.sha256(prompt.encode()).hexdigest(),
    )
    journal.append(LiveCallRecord(**base, status="reserved"))
    journal.append(
        LiveCallRecord(
            **base,
            status=status,  # type: ignore[arg-type]
            actual_provider=f"provider-{model[-1]}",
            actual_model=model,
            cost_usd=Decimal("0.001"),
            latency_ms=latency,
            route_receipt_id=f"evt-{model}-{item}",
            response_hash=hashlib.sha256(f"response:{model}:{item}".encode()).hexdigest(),
            keyword_score=Decimal(score) if status == "ok" else None,
        )
    )


def journals(
    tmp_path: Path,
    *,
    omit_last_b: bool = False,
    fail_first_b: bool = False,
) -> tuple[Journal, NDShadowJournal]:
    calls = Journal(tmp_path / "calls.jsonl")
    definition = suite()
    for model, score in (("model-a", "1"), ("model-b", "0.5")):
        for index, item in enumerate(definition.items):
            if omit_last_b and model == "model-b" and index == len(definition.items) - 1:
                continue
            add_call(
                calls,
                model=model,
                task=item.task_class,
                item=item.item_id,
                prompt=item.prompt,
                score=score,
                latency=10 + index * 10,
                status=("failed" if fail_first_b and model == "model-b" and index == 0 else "ok"),
            )

    class ShadowClient:
        def model_select(self, **kwargs):  # type: ignore[no-untyped-def]
            return NDShadowResponse("model-a", "session", 5)

    class DirectShadowTimeout:
        def run(self, fn, timeout_s):  # type: ignore[no-untyped-def]
            del timeout_s
            return fn()

    shadows = NDShadowJournal(tmp_path / "shadow.jsonl")
    collect_nd_shadow(
        config=NDShadowConfig(
            enabled=True,
            week_id="2026-W28",
            suite_version=definition.suite_version,
            candidates=("model-a", "model-b"),
        ),
        items=tuple((item.item_id, item.task_class, item.prompt) for item in definition.items),
        client=ShadowClient(),
        journal=shadows,
        environ={"ANTIEK_NOTDIAMOND": "1"},
        timeout_runner=DirectShadowTimeout(),
    )
    return calls, shadows


def test_golden_metrics_winners_percentiles_and_disagreements(tmp_path: Path) -> None:
    calls, shadows = journals(tmp_path)
    verdict = build_weekly_verdict(
        week_id="2026-W28",
        wedge_id="wedge",
        suite=suite(),
        call_journal=calls,
        shadow_journal=shadows,
        operator_driver="model-b",
        budget_cap_usd=Decimal("1"),
    )
    distill = next(row for row in verdict.task_verdicts if row.task_class == "distill")
    assert distill.bench_winner == "model-a"
    assert distill.operator_driver == "model-b"
    assert distill.nd_modal_suggestion == "model-a"
    assert distill.nd_sample_size == 2
    assert distill.nd_disagreement_count == 0
    model_a = next(row for row in distill.models if row.model_id == "model-a")
    assert model_a.keyword_proxy_quality == 1
    assert model_a.p50_latency_ms == 10
    assert model_a.p95_latency_ms == 20
    assert model_a.availability == 1
    assert model_a.sample_size == model_a.expected_samples == 2
    assert verdict.auto_promotion is False
    assert verdict.budget_spent_usd == "0.016"
    assert verdict.budget_reserved_usd == "0.000"


def test_incomplete_class_suppresses_winner(tmp_path: Path) -> None:
    calls, shadows = journals(tmp_path, omit_last_b=True)
    verdict = build_weekly_verdict(
        week_id="2026-W28",
        wedge_id="wedge",
        suite=suite(),
        call_journal=calls,
        shadow_journal=shadows,
        operator_driver="model-a",
        budget_cap_usd=Decimal("1"),
    )
    book = next(row for row in verdict.task_verdicts if row.task_class == "book_qa")
    assert book.bench_winner is None
    assert book.winner_suppressed_reason == "incomplete_or_budget_truncated_class"
    assert (
        next(row for row in book.models if row.model_id == "model-b").keyword_proxy_quality is None
    )


def test_zero_call_candidate_still_produces_honest_truncated_verdict(
    tmp_path: Path,
) -> None:
    calls = Journal(tmp_path / "calls.jsonl")
    definition = suite()
    for item in definition.items:
        add_call(
            calls,
            model="model-a",
            task=item.task_class,
            item=item.item_id,
            prompt=item.prompt,
            score="1",
            latency=10,
        )
    verdict = build_weekly_verdict(
        week_id="2026-W28",
        wedge_id="wedge",
        suite=definition,
        call_journal=calls,
        shadow_journal=NDShadowJournal(tmp_path / "shadows.jsonl"),
        operator_driver="model-a",
        budget_cap_usd=Decimal("1"),
        candidate_model_ids=("model-a", "model-b"),
    )
    assert all(row.bench_winner is None for row in verdict.task_verdicts)
    assert all(
        row.winner_suppressed_reason == "incomplete_or_budget_truncated_class"
        for row in verdict.task_verdicts
    )
    assert all(
        next(model for model in row.models if model.model_id == "model-b").sample_size == 0
        for row in verdict.task_verdicts
    )


def test_partial_outage_is_visible_and_cannot_win(tmp_path: Path) -> None:
    calls, shadows = journals(tmp_path, fail_first_b=True)
    verdict = build_weekly_verdict(
        week_id="2026-W28",
        wedge_id="wedge",
        suite=suite(),
        call_journal=calls,
        shadow_journal=shadows,
        operator_driver="model-b",
        budget_cap_usd=Decimal("1"),
    )
    distill = next(row for row in verdict.task_verdicts if row.task_class == "distill")
    assert distill.bench_winner == "model-a"
    assert distill.winner_suppressed_reason is None
    model_b = next(row for row in distill.models if row.model_id == "model-b")
    assert model_b.failure_count == 1
    assert model_b.availability == 0.5
    assert model_b.keyword_proxy_quality == 0.25


def test_over_cap_evidence_suppresses_every_winner(tmp_path: Path) -> None:
    calls, shadows = journals(tmp_path)
    verdict = build_weekly_verdict(
        week_id="2026-W28",
        wedge_id="wedge",
        suite=suite(),
        call_journal=calls,
        shadow_journal=shadows,
        operator_driver="model-a",
        budget_cap_usd=Decimal("0.01"),
    )
    assert verdict.budget_over_cap is True
    assert all(row.bench_winner is None for row in verdict.task_verdicts)
    assert all(
        row.winner_suppressed_reason == "budget_cap_exceeded" for row in verdict.task_verdicts
    )


def test_shadow_variant_must_match_exact_suite_item(tmp_path: Path) -> None:
    calls, shadows = journals(tmp_path)
    definition = suite()
    item = definition.items[0]
    base = dict(
        shadow_id="nds_forged",
        week_id="2026-W28",
        suite_version=definition.suite_version,
        item_id_hash="sha256:" + hashlib.sha256(item.item_id.encode()).hexdigest(),
        task_class="synthesize",
        prompt_hash="sha256:" + hashlib.sha256(b"wrong prompt").hexdigest(),
        candidates=("model-a", "model-b"),
        tradeoff="quality",
    )
    assert shadows.claim(NDShadowRecord(**base, status="pending"))
    assert shadows.settle(NDShadowRecord(**base, status="ok", recommendation="model-b"))
    verdict = build_weekly_verdict(
        week_id="2026-W28",
        wedge_id="wedge",
        suite=definition,
        call_journal=calls,
        shadow_journal=shadows,
        operator_driver="model-a",
        budget_cap_usd=Decimal("1"),
    )
    synthesize = next(row for row in verdict.task_verdicts if row.task_class == "synthesize")
    assert synthesize.nd_sample_size == 2
    assert synthesize.nd_modal_suggestion == "model-a"


class PayloadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture = False
        self.payload = ""

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        values = dict(attrs)
        if tag == "script" and values.get("id") == "antiek-bench-verdict":
            self.capture = True

    def handle_endtag(self, tag):  # type: ignore[no-untyped-def]
        if tag == "script":
            self.capture = False

    def handle_data(self, data):  # type: ignore[no-untyped-def]
        if self.capture:
            self.payload += data


def test_html_is_self_contained_redacted_and_does_not_mutate_suite(tmp_path: Path) -> None:
    calls, shadows = journals(tmp_path)
    registry = SuiteRegistry()
    definition = suite()
    registry.register(definition)
    before = (registry.active_version, tuple(registry.suites))
    verdict = build_weekly_verdict(
        week_id="2026-W28",
        wedge_id="wedge",
        suite=definition,
        call_journal=calls,
        shadow_journal=shadows,
        operator_driver="model-a",
        budget_cap_usd=Decimal("1"),
    )
    rendered = project_weekly_verdict_html(verdict)
    after = (registry.active_version, tuple(registry.suites))
    assert after == before
    assert rendered.startswith("<!doctype html>")
    assert "private distill" not in rendered
    assert "application/pdf" not in rendered.lower()
    assert "auto_promotion=false" in rendered
    assert "operator_acknowledgment_required=true" in rendered
    parser = PayloadParser()
    parser.feed(rendered)
    payload = json.loads(parser.payload)
    assert payload["auto_promotion"] is False
    assert payload["operator_acknowledgment_required"] is True
    assert payload["input_digest"].startswith("sha256:")
