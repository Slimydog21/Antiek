"""Pure tests for fullscreen + draft collective presented twins pack."""

from __future__ import annotations

import pytest

from substrate.fullscreen_draft_collective_presented_twins_compose import (
    FullscreenDraftCollectivePresentedTwinsComposeError,
    compose_fullscreen_draft_collective_presented_twins,
    format_fullscreen_draft_collective_presented_twins_summary,
)
from tests.test_draft_before_merge_collective_presented_twins_compose import (
    COLLECTIVE_PACK,
    DRAFT_GATE,
)

FULLSCREEN = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "highlight": "Scaling laws claim from page 12",
    "prompt": "What evidence supports this?",
    "gated": False,
}

DRAFT_COLLECTIVE = {
    "draft_gate": DRAFT_GATE,
    "collective_pack": COLLECTIVE_PACK,
}


def test_fullscreen_draft_collective_ready():
    c = compose_fullscreen_draft_collective_presented_twins(
        fullscreen=FULLSCREEN,
        draft_collective=DRAFT_COLLECTIVE,
        operator_ack=True,
    )
    assert c.fullscreen.fullscreen_ready is True
    assert c.draft_collective.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.purchase_executed is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "fullscreen_draft_collective_presented_twins_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_fullscreen_draft_collective_presented_twins_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_fullscreen_draft_collective_presented_twins(
        fullscreen=FULLSCREEN,
        draft_collective=DRAFT_COLLECTIVE,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_fullscreen_draft_collective_presented_twins(
        fullscreen={**FULLSCREEN, "session_id": "sess-other"},
        draft_collective=DRAFT_COLLECTIVE,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.merge_executed is False
    assert c.live_dispatched is False


def test_gated_spawn_raises_or_blocks():
    with pytest.raises(FullscreenDraftCollectivePresentedTwinsComposeError):
        compose_fullscreen_draft_collective_presented_twins(
            fullscreen={**FULLSCREEN, "gated": True},
            draft_collective=DRAFT_COLLECTIVE,
            operator_ack=True,
        )


def test_require_operator_ack_type():
    with pytest.raises(FullscreenDraftCollectivePresentedTwinsComposeError):
        compose_fullscreen_draft_collective_presented_twins(
            fullscreen=FULLSCREEN,
            draft_collective=DRAFT_COLLECTIVE,
            operator_ack="yes",  # type: ignore[arg-type]
        )
