"""Pure tests for floating DR residual over draft-before-merge MO price-ceiling pack."""

from __future__ import annotations

from substrate.floating_dr_draft_before_merge_mo_price_ceiling_compose import (
    FloatingDrDraftBeforeMergeMoPriceCeilingComposeError,
    compose_floating_dr_draft_before_merge_mo_price_ceiling,
    format_floating_dr_draft_before_merge_mo_price_ceiling_summary,
)
from tests.test_draft_before_merge_mo_price_ceiling_recursive_twin_compose import (
    DRAFT_GATE,
    MO_PACK,
)

HIGHLIGHT_SURFACE = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "highlight": "scaling laws under noise",
    "gated": False,
    "would_exceed": False,
    "surface_action": "spawn_only",
    "source_families": ["arxiv"],
    "twin_findings": [
        {
            "source_id": "extra-1",
            "body": "claim A supported under noise",
            "kind": "insight",
        },
    ],
    "mark_for_prompt_context": True,
}

DRAFT_PACK = {
    "draft_gate": DRAFT_GATE,
    "mo_pack": MO_PACK,
}


def test_floating_dr_draft_before_merge_ready():
    c = compose_floating_dr_draft_before_merge_mo_price_ceiling(
        highlight_surface=HIGHLIGHT_SURFACE,
        draft_pack=DRAFT_PACK,
        operator_ack=True,
    )
    assert c.highlight_surface.pack_ready is True
    assert c.draft_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.pack_dispatched is False
    assert c.twin_written is False
    assert c.draft_written is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "floating_dr_draft_before_merge_mo_price_ceiling_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_floating_dr_draft_before_merge_mo_price_ceiling_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_floating_dr_draft_before_merge_mo_price_ceiling(
        highlight_surface=HIGHLIGHT_SURFACE,
        draft_pack=DRAFT_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.twin_written is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_floating_dr_draft_before_merge_mo_price_ceiling(
        highlight_surface={**HIGHLIGHT_SURFACE, "session_id": "sess-other"},
        draft_pack=DRAFT_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_gated_highlight_fails_closed():
    try:
        compose_floating_dr_draft_before_merge_mo_price_ceiling(
            highlight_surface={**HIGHLIGHT_SURFACE, "gated": True},
            draft_pack=DRAFT_PACK,
            operator_ack=True,
        )
        raise AssertionError("expected gated fail-closed")
    except FloatingDrDraftBeforeMergeMoPriceCeilingComposeError as e:
        assert "gated" in str(e).lower()
