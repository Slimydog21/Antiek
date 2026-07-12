"""Pure tests for MO unattended over fullscreen draft multi-select pack."""

from __future__ import annotations

from substrate.mo_unattended_fullscreen_draft_before_merge_multiselect_compose import (
    compose_mo_unattended_fullscreen_draft_before_merge_multiselect,
    format_mo_unattended_fullscreen_draft_before_merge_multiselect_summary,
)
from tests.test_fullscreen_draft_before_merge_floating_multiselect_compose import (
    DRAFT_PACK,
    FULLSCREEN,
)

MO = {
    "operator_id": "op-1",
    "work_minutes": 120,
    "goals": [
        {"goal_id": "g1", "title": "Map scaling-law residual gaps"},
        {"goal_id": "g2", "title": "Synthesize twin search hits"},
    ],
    "usd_per_hour": 15,
    "approved_ceiling_usd": 50,
    "unattended_ack": True,
    "spend_consent": True,
    "brief_dispatch_ready": True,
}

FULLSCREEN_PACK = {
    "fullscreen": FULLSCREEN,
    "draft_pack": DRAFT_PACK,
}


def test_mo_unattended_fullscreen_ready():
    c = compose_mo_unattended_fullscreen_draft_before_merge_multiselect(
        mo=MO,
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.mo.unattended_package_ready is True
    assert c.fullscreen_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
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
        == "mo_unattended_fullscreen_draft_before_merge_multiselect_compose_advisory"
    )
    assert "live_execution_authorized=false" in (
        format_mo_unattended_fullscreen_draft_before_merge_multiselect_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_mo_unattended_fullscreen_draft_before_merge_multiselect(
        mo=MO,
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_unattended_ack_false_blocks():
    c = compose_mo_unattended_fullscreen_draft_before_merge_multiselect(
        mo={**MO, "unattended_ack": False},
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.mo.unattended_package_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_spend_consent_false_blocks():
    c = compose_mo_unattended_fullscreen_draft_before_merge_multiselect(
        mo={**MO, "spend_consent": False},
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.mo.unattended_package_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"
