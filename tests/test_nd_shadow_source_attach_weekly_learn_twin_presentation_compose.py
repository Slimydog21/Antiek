"""Pure tests for ND shadow REJECT over source-attach weekly learn twin presentation."""

from __future__ import annotations

from substrate.nd_shadow_source_attach_weekly_learn_twin_presentation_compose import (
    compose_nd_shadow_source_attach_weekly_learn_twin_presentation,
    format_nd_shadow_source_attach_weekly_learn_twin_presentation_summary,
)
from tests.test_source_attach_antiek_bench_weekly_learn_twin_presentation_compose import (
    SOURCES,
    WEEKLY_PACK,
)

ND_SHADOW = {
    "selected_model_id": "gpt-5.5",
    "nd_recommended_model_id": "claude-opus",
    "kill_switch_on": True,
    "confidence": 0.72,
    "task": "deep_research",
    "inventory_model_ids": ["gpt-5.5", "claude-opus", "mimo"],
}

SOURCE_PACK = {
    "sources": SOURCES,
    "weekly_pack": WEEKLY_PACK,
}


def test_nd_shadow_source_attach_weekly_learn_ready():
    c = compose_nd_shadow_source_attach_weekly_learn_twin_presentation(
        nd_shadow=ND_SHADOW,
        source_pack=SOURCE_PACK,
        operator_ack=True,
    )
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.nd_shadow.live_router_authorized is False
    assert c.source_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.suite_rewritten is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.pdf_primary is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "nd_shadow_source_attach_weekly_learn_twin_presentation_compose_advisory"
    )
    assert "live_router_authorized=false" in (
        format_nd_shadow_source_attach_weekly_learn_twin_presentation_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_nd_shadow_source_attach_weekly_learn_twin_presentation(
        nd_shadow=ND_SHADOW,
        source_pack=SOURCE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.remote_fetched is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks_source_pack():
    c = compose_nd_shadow_source_attach_weekly_learn_twin_presentation(
        nd_shadow=ND_SHADOW,
        source_pack={
            **SOURCE_PACK,
            "sources": {**SOURCES, "would_exceed": True},
        },
        operator_ack=True,
    )
    assert c.source_pack.sources.pack_ready is False
    assert c.source_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_nd_shadow_source_attach_weekly_learn_twin_presentation(
        nd_shadow=ND_SHADOW,
        source_pack={
            **SOURCE_PACK,
            "sources": {**SOURCES, "session_id": "sess-other"},
        },
        operator_ack=True,
    )
    assert c.source_pack.session_aligned is False
    assert c.source_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.production_router_verdict == "REJECT"
