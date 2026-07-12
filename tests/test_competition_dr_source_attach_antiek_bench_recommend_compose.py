"""Pure tests for competition DR over source-attach Antiek-bench recommend pack."""

from __future__ import annotations

from substrate.competition_dr_source_attach_antiek_bench_recommend_compose import (
    compose_competition_dr_source_attach_antiek_bench_recommend,
    format_competition_dr_source_attach_antiek_bench_recommend_summary,
)
from tests.test_competition_dr_quality_source_pack_compose import (
    CITATIONS,
    DECISIONS,
)
from tests.test_source_attach_antiek_bench_recommend_mo_unattended_compose import (
    RECOMMEND_PACK,
    SOURCES,
)

COMPETITION = {
    "session_id": "sess-1",
    "competitor_decisions": DECISIONS,
    "requested_families": ["arxiv", "substack"],
    "citations": CITATIONS,
    "quality_overall": 0.8,
    "quality_floor": 0.5,
    "would_exceed": False,
}

SOURCE_PACK = {
    "sources": SOURCES,
    "recommend_pack": RECOMMEND_PACK,
}


def test_competition_dr_source_attach_recommend_ready():
    c = compose_competition_dr_source_attach_antiek_bench_recommend(
        competition=COMPETITION,
        source_pack=SOURCE_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is True
    assert c.source_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_primary is False
    assert c.suite_rewritten is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.live_router_authorized is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "competition_dr_source_attach_antiek_bench_recommend_compose_advisory"
    )
    assert "live_dispatch_authorized=false" in (
        format_competition_dr_source_attach_antiek_bench_recommend_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_competition_dr_source_attach_antiek_bench_recommend(
        competition=COMPETITION,
        source_pack=SOURCE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_competition_dr_source_attach_antiek_bench_recommend(
        competition={**COMPETITION, "session_id": "sess-other"},
        source_pack=SOURCE_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_quality_below_floor_blocks():
    c = compose_competition_dr_source_attach_antiek_bench_recommend(
        competition={
            **COMPETITION,
            "quality_overall": 0.2,
            "quality_floor": 0.5,
        },
        source_pack=SOURCE_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.suite_rewritten is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"
