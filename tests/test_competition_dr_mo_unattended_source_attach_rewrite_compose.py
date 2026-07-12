"""Pure tests for competition DR residual over MO unattended source-attach rewrite."""

from __future__ import annotations

from substrate.competition_dr_mo_unattended_source_attach_rewrite_compose import (
    compose_competition_dr_mo_unattended_source_attach_rewrite,
    format_competition_dr_mo_unattended_source_attach_rewrite_summary,
)
from tests.test_mo_unattended_source_attach_antiek_bench_rewrite_compose import (
    MO,
    RESEARCH_PACK,
)

COMPETITION = {
    "session_id": "sess-1",
    "competitor_decisions": [
        {
            "competitor": "Perplexity",
            "area": "citation_grounding",
            "decision_summary": "Inline citations with source cards",
            "antiek_status": "parity",
        },
        {
            "competitor": "OpenAI DR",
            "area": "multi_agent_orchestration",
            "decision_summary": "Planner + browser agents",
            "antiek_status": "behind",
            "residual": "strengthen collective floating cohesive pack",
        },
    ],
    "requested_families": ["arxiv", "substack"],
    "citations": [
        {
            "citation_id": "c1",
            "family": "arxiv",
            "title": "Scaling Laws under Noise",
            "external_id": "arxiv:2301.00001",
        },
        {
            "citation_id": "c2",
            "family": "substack",
            "title": "Research notes on evals",
            "url": "https://example.substack.com/p/evals",
        },
    ],
    "quality_overall": 0.85,
    "quality_floor": 0.5,
    "would_exceed": False,
}

MO_PACK = {
    "mo": MO,
    "research_pack": RESEARCH_PACK,
}


def test_competition_mo_unattended_ready():
    c = compose_competition_dr_mo_unattended_source_attach_rewrite(
        competition=COMPETITION,
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is True
    assert c.mo_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "competition_dr_mo_unattended_source_attach_rewrite_compose_advisory"
    )
    assert "live_dispatch_authorized=false" in (
        format_competition_dr_mo_unattended_source_attach_rewrite_summary(c)
    ) or "pack_ready=true" in (
        format_competition_dr_mo_unattended_source_attach_rewrite_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_competition_dr_mo_unattended_source_attach_rewrite(
        competition=COMPETITION,
        mo_pack=MO_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_competition_dr_mo_unattended_source_attach_rewrite(
        competition={**COMPETITION, "session_id": "sess-other"},
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_competition_dr_mo_unattended_source_attach_rewrite(
        competition={**COMPETITION, "would_exceed": True},
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.production_router_verdict == "REJECT"
