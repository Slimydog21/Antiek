"""Pure tests for fullscreen-open residual over collective multiselect floating DR pack."""

from __future__ import annotations

import pytest

from substrate.fullscreen_open_collective_multiselect_floating_dr_compose import (
    FullscreenOpenCollectiveMultiselectFloatingDrComposeError,
    compose_fullscreen_open_collective_multiselect_floating_dr,
    format_fullscreen_open_collective_multiselect_floating_dr_summary,
)
from tests.test_collective_multiselect_floating_dr_draft_before_merge_compose import (
    FLOATING_DR_PACK,
    MULTISELECT,
)

FULLSCREEN = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "highlight": "Scaling laws claim from page 12",
    "prompt": "What evidence supports this?",
    "gated": False,
}

COLLECTIVE_PACK = {
    "multiselect": MULTISELECT,
    "floating_dr_pack": FLOATING_DR_PACK,
}


def test_fullscreen_collective_multiselect_ready():
    c = compose_fullscreen_open_collective_multiselect_floating_dr(
        fullscreen=FULLSCREEN,
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.fullscreen.fullscreen_ready is True
    assert c.collective_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.merge_executed is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.analysis_written is False
    assert c.twin_written is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "fullscreen_open_collective_multiselect_floating_dr_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_fullscreen_open_collective_multiselect_floating_dr_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_fullscreen_open_collective_multiselect_floating_dr(
        fullscreen=FULLSCREEN,
        collective_pack=COLLECTIVE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_fullscreen_open_collective_multiselect_floating_dr(
        fullscreen={**FULLSCREEN, "session_id": "sess-other"},
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_gated_highlight_fails_closed():
    with pytest.raises(
        FullscreenOpenCollectiveMultiselectFloatingDrComposeError
    ) as ei:
        compose_fullscreen_open_collective_multiselect_floating_dr(
            fullscreen={**FULLSCREEN, "gated": True},
            collective_pack=COLLECTIVE_PACK,
            operator_ack=True,
        )
    assert "gated" in str(ei.value).lower()
