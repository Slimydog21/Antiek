"""Pure tests for recursive twin presentation over write twin collective MO."""

from __future__ import annotations

from substrate.recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose import (
    compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin,
    format_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_summary,
)
from tests.test_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose import (
    FULLSCREEN_PACK,
    WRITE,
)

TWIN = {
    "parent_asset_id": "book-1",
    "source_excerpt": (
        "<p>Scaling laws hold under noise in compute-optimal regimes.</p>"
    ),
    "focus_questions": ["Where does it break?", "What residual gaps?"],
    "existing_twin_asset_id": "twin-book-1",
}

PRESENTATION = {
    "view_mode": "side_panel",
    "open_requested": True,
    "merge_to_parent_preview": False,
    "presented_insights": [
        "scaling laws hold under noise in compute-optimal regimes",
    ],
    "presented_questions": [
        "Where does scaling break under distribution shift?",
    ],
}

WRITE_PACK = {
    "write": WRITE,
    "fullscreen_pack": FULLSCREEN_PACK,
}


def test_recursive_twin_presentation_write_collective_ready():
    c = compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin(
        twin=TWIN,
        presentation=PRESENTATION,
        write_pack=WRITE_PACK,
        operator_ack=True,
    )
    assert c.twin.twin_propose_ready is True
    assert c.presentation.presentation_ready is True
    assert c.write_pack.pack_ready is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.twin_written is False
    assert c.prompts_injected is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.live_dispatched is False
    assert c.live_execution_authorized is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_advisory"
    )
    assert "twin_written=false" in (
        format_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_summary(
            c
        )
    )


def test_operator_ack_false_blocks():
    c = compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin(
        twin=TWIN,
        presentation=PRESENTATION,
        write_pack=WRITE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.presentation.presentation_ready is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_open_requested_false_blocks_presentation():
    c = compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin(
        twin=TWIN,
        presentation={**PRESENTATION, "open_requested": False},
        write_pack=WRITE_PACK,
        operator_ack=True,
    )
    assert c.presentation.presentation_ready is False
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    c = compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin(
        twin={**TWIN, "parent_asset_id": "other-book"},
        presentation=PRESENTATION,
        write_pack=WRITE_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"
