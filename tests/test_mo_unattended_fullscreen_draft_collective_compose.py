"""Pure tests for MO unattended + fullscreen draft collective pack."""

from __future__ import annotations

import pytest

from substrate.mo_unattended_fullscreen_draft_collective_compose import (
    MoUnattendedFullscreenDraftCollectiveComposeError,
    compose_mo_unattended_fullscreen_draft_collective,
    format_mo_unattended_fullscreen_draft_collective_summary,
)
from tests.test_fullscreen_draft_collective_presented_twins_compose import (
    DRAFT_COLLECTIVE,
    FULLSCREEN,
)

MO = {
    "operator_id": "op-1",
    "work_minutes": 120,
    "goals": [
        {"goal_id": "g1", "title": "Map arxiv competition gaps"},
        {"goal_id": "g2", "title": "Synthesize twin notes"},
    ],
    "usd_per_hour": 15,
    "approved_ceiling_usd": 40,
    "unattended_ack": True,
    "spend_consent": True,
    "brief_dispatch_ready": True,
}

FULLSCREEN_PACK = {
    "fullscreen": FULLSCREEN,
    "draft_collective": DRAFT_COLLECTIVE,
}


def test_mo_unattended_fullscreen_ready():
    c = compose_mo_unattended_fullscreen_draft_collective(
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
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "mo_unattended_fullscreen_draft_collective_compose_advisory"
    )
    assert "live_execution_authorized=false" in (
        format_mo_unattended_fullscreen_draft_collective_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_mo_unattended_fullscreen_draft_collective(
        mo=MO,
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_spend_consent_false_blocks():
    c = compose_mo_unattended_fullscreen_draft_collective(
        mo={**MO, "spend_consent": False},
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.mo.unattended_package_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False


def test_unattended_ack_false_blocks():
    c = compose_mo_unattended_fullscreen_draft_collective(
        mo={**MO, "unattended_ack": False},
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.mo.unattended_package_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False


def test_require_operator_ack_type():
    with pytest.raises(MoUnattendedFullscreenDraftCollectiveComposeError):
        compose_mo_unattended_fullscreen_draft_collective(
            mo=MO,
            fullscreen_pack=FULLSCREEN_PACK,
            operator_ack="yes",  # type: ignore[arg-type]
        )
