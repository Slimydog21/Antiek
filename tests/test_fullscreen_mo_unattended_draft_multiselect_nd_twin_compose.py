"""Pure tests for fullscreen over MO unattended draft multiselect ND twin."""

from __future__ import annotations

from substrate.fullscreen_mo_unattended_draft_multiselect_nd_twin_compose import (
    compose_fullscreen_mo_unattended_draft_multiselect_nd_twin,
    format_fullscreen_mo_unattended_draft_multiselect_nd_twin_summary,
)
from tests.test_mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose import (
    DRAFT_PACK,
    MO,
)

FULLSCREEN = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "highlight": "Scaling laws claim from page 12",
    "prompt": "What evidence supports this?",
    "gated": False,
}

MO_PACK = {
    "mo": MO,
    "draft_pack": DRAFT_PACK,
}


def test_fullscreen_mo_unattended_draft_nd_twin_ready():
    c = compose_fullscreen_mo_unattended_draft_multiselect_nd_twin(
        fullscreen=FULLSCREEN,
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.fullscreen.fullscreen_ready is True
    assert c.mo_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.live_execution_authorized is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_fullscreen_mo_unattended_draft_multiselect_nd_twin_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_fullscreen_mo_unattended_draft_multiselect_nd_twin(
        fullscreen=FULLSCREEN,
        mo_pack=MO_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_fullscreen_mo_unattended_draft_multiselect_nd_twin(
        fullscreen={**FULLSCREEN, "session_id": "sess-other"},
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_spend_consent_false_blocks():
    c = compose_fullscreen_mo_unattended_draft_multiselect_nd_twin(
        fullscreen=FULLSCREEN,
        mo_pack={"mo": {**MO, "spend_consent": False}, "draft_pack": DRAFT_PACK},
        operator_ack=True,
    )
    assert c.mo_pack.mo.unattended_package_ready is False
    assert c.mo_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"
