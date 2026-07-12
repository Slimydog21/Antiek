"""Pure tests for Antiek-bench rewrite residual over model decision marketplace."""

from __future__ import annotations

from substrate.antiek_bench_rewrite_model_decision_marketplace_compose import (
    compose_antiek_bench_rewrite_model_decision_marketplace,
    format_antiek_bench_rewrite_model_decision_marketplace_summary,
)
from tests.test_model_decision_twin_search_html_native_marketplace_compose import (
    DECISION,
    TWIN_SEARCH_PACK,
)

REWRITE_READY = {
    "week_label": "2026-W28",
    "patterns": [
        {
            "task_family": "deep_research",
            "model_id": "gpt-5",
            "outcome": "failed",
            "n": 3,
        },
        {
            "task_family": "deep_research",
            "model_id": "mimo-v2",
            "outcome": "mixed",
            "n": 2,
        },
        {
            "task_family": "twin_notes",
            "model_id": "claude",
            "outcome": "worked",
            "n": 4,
        },
    ],
}

REWRITE_EMPTY = {
    "week_label": "2026-W28",
    "patterns": [
        {
            "task_family": "twin_notes",
            "model_id": "claude",
            "outcome": "worked",
            "n": 4,
        },
    ],
}

MODEL_DECISION_PACK = {
    "decision": DECISION,
    "twin_search_pack": TWIN_SEARCH_PACK,
}


def test_rewrite_residual_model_decision_ready():
    c = compose_antiek_bench_rewrite_model_decision_marketplace(
        rewrite=REWRITE_READY,
        model_decision_pack=MODEL_DECISION_PACK,
        operator_ack=True,
    )
    assert c.proposal_count >= 1
    assert c.rewrite.applied is False
    assert c.suite_rewritten is False
    assert c.applied is False
    assert c.model_decision_pack.pack_ready is True
    assert c.model_decision_pack.decision.would_exceed is False
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.live_meter_read is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "antiek_bench_rewrite_model_decision_marketplace_compose_advisory"
    )
    assert "suite_rewritten=false" in (
        format_antiek_bench_rewrite_model_decision_marketplace_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_antiek_bench_rewrite_model_decision_marketplace(
        rewrite=REWRITE_READY,
        model_decision_pack=MODEL_DECISION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.suite_rewritten is False
    assert c.applied is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_zero_proposals_blocks():
    c = compose_antiek_bench_rewrite_model_decision_marketplace(
        rewrite=REWRITE_EMPTY,
        model_decision_pack=MODEL_DECISION_PACK,
        operator_ack=True,
    )
    assert c.proposal_count == 0
    assert c.pack_ready is False
    assert c.suite_rewritten is False
    assert c.applied is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_antiek_bench_rewrite_model_decision_marketplace(
        rewrite=REWRITE_READY,
        model_decision_pack={
            "decision": {
                **DECISION,
                "projected_cost_usd_high": 100,
                "daily_cap_usd": 50,
                "spent_usd": 10,
            },
            "twin_search_pack": TWIN_SEARCH_PACK,
        },
        operator_ack=True,
    )
    assert c.model_decision_pack.decision.would_exceed is True
    assert c.pack_ready is False
    assert c.suite_rewritten is False
    assert c.applied is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
