"""Pure tests for Antiek-bench recommend + source attach settings MO pack."""

from __future__ import annotations

import pytest

from substrate.antiek_bench_source_attach_settings_mo_compose import (
    AntiekBenchSourceAttachSettingsMoComposeError,
    compose_antiek_bench_source_attach_settings_mo,
    format_antiek_bench_source_attach_settings_mo_summary,
)
from tests.test_source_attach_settings_decision_mo_compose import (
    SETTINGS_MO,
    SOURCES,
)

BENCH = {
    "week_id": "2026-W28",
    "focus_task": "deep_research",
    "events": [
        {
            "event_id": "e1",
            "task": "deep_research",
            "model_id": "gpt-5.5",
            "outcome": "worked",
            "score": 0.9,
        },
        {
            "event_id": "e2",
            "task": "deep_research",
            "model_id": "gpt-5.5",
            "outcome": "worked",
            "score": 0.85,
        },
        {
            "event_id": "e3",
            "task": "deep_research",
            "model_id": "mimo-v2",
            "outcome": "failed",
            "score": 0.2,
        },
        {
            "event_id": "e4",
            "task": "deep_research",
            "model_id": "mimo-v2",
            "outcome": "failed",
            "score": 0.3,
        },
        {
            "event_id": "e5",
            "task": "twin_notes",
            "model_id": "grok-4.5",
            "outcome": "worked",
            "score": 0.8,
        },
        {
            "event_id": "e6",
            "task": "twin_notes",
            "model_id": "grok-4.5",
            "outcome": "worked",
            "score": 0.75,
        },
    ],
    "models": [
        {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.5},
        {"model_id": "grok-4.5", "projected_cost_usd_high": 0.3},
        {"model_id": "mimo-v2", "projected_cost_usd_high": 0.1},
    ],
    "daily_cap_usd": 20,
    "spent_usd": 5,
    "projected_cost_usd_high": 0.5,
    "existing_tasks": ["deep_research", "twin_notes"],
}

SOURCE_PACK = {
    "sources": SOURCES,
    "settings_mo": SETTINGS_MO,
}


def test_bench_source_attach_ready():
    c = compose_antiek_bench_source_attach_settings_mo(
        bench=BENCH,
        source_pack=SOURCE_PACK,
        operator_ack=True,
    )
    assert c.bench.pack_ready is True
    assert c.bench.recommendation is not None
    assert c.bench.recommendation.recommended_model_id == "gpt-5.5"
    assert c.source_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.live_execution_authorized is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "antiek_bench_source_attach_settings_mo_compose_advisory"
    )
    assert "live_router_authorized=false" in (
        format_antiek_bench_source_attach_settings_mo_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_antiek_bench_source_attach_settings_mo(
        bench=BENCH,
        source_pack=SOURCE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"


def test_source_session_mismatch_blocks():
    c = compose_antiek_bench_source_attach_settings_mo(
        bench=BENCH,
        source_pack={
            **SOURCE_PACK,
            "sources": {**SOURCES, "session_id": "sess-other"},
        },
        operator_ack=True,
    )
    assert c.source_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.suite_rewritten is False


def test_high_min_events_null_rec_still_pure():
    c = compose_antiek_bench_source_attach_settings_mo(
        bench={**BENCH, "min_events_for_recommendation": 100},
        source_pack=SOURCE_PACK,
        operator_ack=True,
    )
    assert c.bench.recommendation is None
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_require_operator_ack_type():
    with pytest.raises(AntiekBenchSourceAttachSettingsMoComposeError):
        compose_antiek_bench_source_attach_settings_mo(
            bench=BENCH,
            source_pack=SOURCE_PACK,
            operator_ack="yes",  # type: ignore[arg-type]
        )
