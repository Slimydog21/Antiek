"""Pure tests for Antiek-bench recommend over MO unattended fullscreen draft pack."""

from __future__ import annotations

from substrate.antiek_bench_recommend_mo_unattended_fullscreen_draft_compose import (
    compose_antiek_bench_recommend_mo_unattended_fullscreen_draft,
    format_antiek_bench_recommend_mo_unattended_fullscreen_draft_summary,
)
from tests.test_antiek_bench_task_model_recommendation_compose import (
    MODELS,
    _events,
)
from tests.test_mo_unattended_fullscreen_draft_before_merge_multiselect_compose import (
    FULLSCREEN_PACK,
    MO,
)

BENCH = {
    "week_id": "2026-W28",
    "focus_task": "deep_research",
    "events": _events(),
    "models": MODELS,
    "daily_cap_usd": 20,
    "spent_usd": 5,
    "projected_cost_usd_high": 0.5,
    "existing_tasks": ["deep_research", "twin_notes"],
}

MO_PACK = {
    "mo": MO,
    "fullscreen_pack": FULLSCREEN_PACK,
}


def test_antiek_bench_recommend_mo_unattended_fullscreen_ready():
    c = compose_antiek_bench_recommend_mo_unattended_fullscreen_draft(
        bench=BENCH,
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.bench.pack_ready is True
    assert c.bench.recommendation is not None
    assert c.bench.recommendation.recommended_model_id == "gpt-5.5"
    assert c.mo_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.operator_id == "op-1"
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.backlog_mutated is False
    assert c.store_mutated is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "antiek_bench_recommend_mo_unattended_fullscreen_draft_compose_advisory"
    )
    assert "live_router_authorized=false" in (
        format_antiek_bench_recommend_mo_unattended_fullscreen_draft_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_antiek_bench_recommend_mo_unattended_fullscreen_draft(
        bench=BENCH,
        mo_pack=MO_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.live_execution_authorized is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"


def test_unattended_ack_false_blocks():
    c = compose_antiek_bench_recommend_mo_unattended_fullscreen_draft(
        bench=BENCH,
        mo_pack={
            **MO_PACK,
            "mo": {**MO, "unattended_ack": False},
        },
        operator_ack=True,
    )
    assert c.mo_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_insufficient_bench_events_honesty():
    c = compose_antiek_bench_recommend_mo_unattended_fullscreen_draft(
        bench={
            **BENCH,
            "events": [
                {
                    "event_id": "e1",
                    "task": "deep_research",
                    "model_id": "gpt-5.5",
                    "outcome": "worked",
                    "score": 0.9,
                }
            ],
            "min_events_for_recommendation": 2,
        },
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.bench.recommendation is None
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"
