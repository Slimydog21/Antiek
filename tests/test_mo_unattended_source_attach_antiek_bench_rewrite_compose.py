"""Pure tests for MO unattended residual over source-attach Antiek-bench rewrite."""

from __future__ import annotations

from substrate.mo_unattended_source_attach_antiek_bench_rewrite_compose import (
    compose_mo_unattended_source_attach_antiek_bench_rewrite,
    format_mo_unattended_source_attach_antiek_bench_rewrite_summary,
)
from tests.test_source_attach_antiek_bench_rewrite_model_decision_compose import (
    REWRITE_PACK,
    SOURCES,
)
from tests.test_antiek_bench_rewrite_model_decision_marketplace_compose import (
    MODEL_DECISION_PACK,
    REWRITE_EMPTY,
)

MO = {
    "operator_id": "op-1",
    "work_minutes": 120,
    "goals": [
        {"goal_id": "g1", "title": "Map arxiv competition gaps"},
        {"goal_id": "g2", "title": "Synthesize twin notes"},
    ],
    "usd_per_hour": 15,
    "approved_ceiling_usd": 50,
    "price_ceiling_ack": True,
    "unattended_ack": True,
    "spend_consent": True,
    "stage": "unattended_pack",
}

RESEARCH_PACK = {
    "sources": SOURCES,
    "rewrite_pack": REWRITE_PACK,
}


def test_mo_unattended_source_attach_rewrite_ready():
    c = compose_mo_unattended_source_attach_antiek_bench_rewrite(
        mo=MO,
        research_pack=RESEARCH_PACK,
        operator_ack=True,
    )
    assert c.mo.pack_ready is True
    assert c.research_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.remote_fetched is False
    assert c.suite_rewritten is False
    assert c.pdf_primary is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "mo_unattended_source_attach_antiek_bench_rewrite_compose_advisory"
    )
    assert "live_execution_authorized=false" in (
        format_mo_unattended_source_attach_antiek_bench_rewrite_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_mo_unattended_source_attach_antiek_bench_rewrite(
        mo=MO,
        research_pack=RESEARCH_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_low_ceiling_blocks():
    c = compose_mo_unattended_source_attach_antiek_bench_rewrite(
        mo={
            **MO,
            "approved_ceiling_usd": 1,
            "below_recommend_override": False,
        },
        research_pack=RESEARCH_PACK,
        operator_ack=True,
    )
    assert c.mo.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_zero_proposals_blocks():
    c = compose_mo_unattended_source_attach_antiek_bench_rewrite(
        mo=MO,
        research_pack={
            "sources": SOURCES,
            "rewrite_pack": {
                "rewrite": REWRITE_EMPTY,
                "model_decision_pack": MODEL_DECISION_PACK,
            },
        },
        operator_ack=True,
    )
    assert c.research_pack.rewrite_pack.proposal_count == 0
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"
