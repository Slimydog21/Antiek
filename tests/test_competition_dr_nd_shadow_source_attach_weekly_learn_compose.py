"""Pure tests for competition DR over ND shadow source-attach weekly learn."""

from __future__ import annotations

from substrate.competition_dr_nd_shadow_source_attach_weekly_learn_compose import (
    compose_competition_dr_nd_shadow_source_attach_weekly_learn,
    format_competition_dr_nd_shadow_source_attach_weekly_learn_summary,
)
from tests.test_nd_shadow_source_attach_weekly_learn_twin_presentation_compose import (
    ND_SHADOW,
    SOURCE_PACK,
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
    "quality_overall": 0.8,
    "quality_floor": 0.5,
    "would_exceed": False,
}

ND_PACK = {
    "nd_shadow": ND_SHADOW,
    "source_pack": SOURCE_PACK,
}


def test_competition_dr_nd_shadow_source_attach_ready():
    c = compose_competition_dr_nd_shadow_source_attach_weekly_learn(
        competition=COMPETITION,
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is True
    assert c.nd_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.pdf_primary is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
    assert c.nd_pack.nd_shadow.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "competition_dr_nd_shadow_source_attach_weekly_learn_compose_advisory"
    )
    assert "live_dispatch_authorized=false" in (
        format_competition_dr_nd_shadow_source_attach_weekly_learn_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_competition_dr_nd_shadow_source_attach_weekly_learn(
        competition=COMPETITION,
        nd_pack=ND_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_competition_dr_nd_shadow_source_attach_weekly_learn(
        competition={**COMPETITION, "session_id": "sess-other"},
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks_competition():
    c = compose_competition_dr_nd_shadow_source_attach_weekly_learn(
        competition={**COMPETITION, "would_exceed": True},
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
