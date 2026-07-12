"""Pure tests for competition DR over settings add-model bench source MO pack."""

from __future__ import annotations

from substrate.competition_dr_settings_add_model_bench_source_mo_compose import (
    compose_competition_dr_settings_add_model_bench_source_mo,
    format_competition_dr_settings_add_model_bench_source_mo_summary,
)
from tests.test_settings_add_model_antiek_bench_source_attach_mo_compose import (
    BENCH_PACK,
    SETTINGS,
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

SETTINGS_PACK = {
    "settings": SETTINGS,
    "bench_pack": BENCH_PACK,
}


def test_competition_settings_ready():
    c = compose_competition_dr_settings_add_model_bench_source_mo(
        competition=COMPETITION,
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is True
    assert c.settings_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.live_execution_authorized is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "competition_dr_settings_add_model_bench_source_mo_compose_advisory"
    )
    assert "live_dispatch_authorized=false" in (
        format_competition_dr_settings_add_model_bench_source_mo_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_competition_dr_settings_add_model_bench_source_mo(
        competition=COMPETITION,
        settings_pack=SETTINGS_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_competition_dr_settings_add_model_bench_source_mo(
        competition={**COMPETITION, "session_id": "sess-other"},
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_competition_dr_settings_add_model_bench_source_mo(
        competition={**COMPETITION, "would_exceed": True},
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"
