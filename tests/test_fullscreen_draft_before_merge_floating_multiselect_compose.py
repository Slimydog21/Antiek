"""Pure tests for fullscreen over draft-before-merge floating multi-select pack."""

from __future__ import annotations

from substrate.fullscreen_draft_before_merge_floating_multiselect_compose import (
    compose_fullscreen_draft_before_merge_floating_multiselect,
    format_fullscreen_draft_before_merge_floating_multiselect_summary,
)
from tests.test_draft_before_merge_floating_multiselect_model_decision_compose import (
    DRAFT_GATE,
    MULTI_PACK,
)
from tests.test_floating_multiselect_model_decision_twin_search_free_settings_compose import (
    DECISION,
    DECISION_PACK,
)

FULLSCREEN = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "highlight": "Scaling laws claim from page 12",
    "prompt": "What evidence supports this?",
    "gated": False,
}

DRAFT_PACK = {
    "draft_gate": DRAFT_GATE,
    "multi_pack": MULTI_PACK,
}


def test_fullscreen_draft_before_merge_ready():
    c = compose_fullscreen_draft_before_merge_floating_multiselect(
        fullscreen=FULLSCREEN,
        draft_pack=DRAFT_PACK,
        operator_ack=True,
    )
    assert c.fullscreen.fullscreen_ready is True
    assert c.draft_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "fullscreen_draft_before_merge_floating_multiselect_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_fullscreen_draft_before_merge_floating_multiselect_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_fullscreen_draft_before_merge_floating_multiselect(
        fullscreen=FULLSCREEN,
        draft_pack=DRAFT_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_fullscreen_draft_before_merge_floating_multiselect(
        fullscreen={**FULLSCREEN, "session_id": "sess-other"},
        draft_pack=DRAFT_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_fullscreen_draft_before_merge_floating_multiselect(
        fullscreen=FULLSCREEN,
        draft_pack={
            **DRAFT_PACK,
            "multi_pack": {
                **MULTI_PACK,
                "decision_pack": {
                    **DECISION_PACK,
                    "decision": {
                        **DECISION,
                        "projected_cost_usd_high": 100,
                        "daily_cap_usd": 50,
                        "spent_usd": 10,
                    },
                },
            },
        },
        operator_ack=True,
    )
    assert c.draft_pack.multi_pack.decision_pack.decision.would_exceed is True
    assert c.draft_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"
