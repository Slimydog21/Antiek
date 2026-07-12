"""Pure tests for recursive twin presentation + competition DR source-attach pack."""

from __future__ import annotations

import pytest

from substrate.recursive_twin_presentation_competition_dr_source_attach_compose import (
    RecursiveTwinPresentationCompetitionDrSourceAttachComposeError,
    compose_recursive_twin_presentation_competition_dr_source_attach,
    format_recursive_twin_presentation_competition_dr_source_attach_summary,
)
from tests.test_competition_dr_source_attach_antiek_bench_recommend_compose import (
    COMPETITION,
    SOURCE_PACK,
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

COMPETITION_PACK = {
    "competition": COMPETITION,
    "source_pack": SOURCE_PACK,
}


def test_twin_presentation_competition_source_attach_ready():
    c = compose_recursive_twin_presentation_competition_dr_source_attach(
        twin=TWIN,
        presentation=PRESENTATION,
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.twin.twin_propose_ready is True
    assert c.presentation.presentation_ready is True
    assert c.presentation.view_mode == "side_panel"
    assert c.presentation.presented_insight_count == 1
    assert c.presentation.presented_question_count == 1
    assert c.competition_pack.pack_ready is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.twin_written is False
    assert c.prompts_injected is False
    assert c.merge_executed is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_primary is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.suite_rewritten is False
    assert c.live_router_authorized is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "recursive_twin_presentation_competition_dr_source_attach_compose_advisory"
    )
    assert "twin_written=false" in (
        format_recursive_twin_presentation_competition_dr_source_attach_summary(c)
    )
    assert len(c.presentation.presentation_sections) > 3


def test_operator_ack_false_blocks():
    c = compose_recursive_twin_presentation_competition_dr_source_attach(
        twin=TWIN,
        presentation=PRESENTATION,
        competition_pack=COMPETITION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.presentation.presentation_ready is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_open_requested_false_blocks():
    c = compose_recursive_twin_presentation_competition_dr_source_attach(
        twin=TWIN,
        presentation={**PRESENTATION, "open_requested": False},
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.presentation.presentation_ready is False
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.purchase_executed is False


def test_parent_mismatch_blocks():
    c = compose_recursive_twin_presentation_competition_dr_source_attach(
        twin={**TWIN, "parent_asset_id": "book-other"},
        presentation=PRESENTATION,
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.merge_executed is False
    assert c.pdf_primary is False


def test_overlay_merge_preview_still_pure():
    c = compose_recursive_twin_presentation_competition_dr_source_attach(
        twin=TWIN,
        presentation={
            **PRESENTATION,
            "view_mode": "overlay",
            "merge_to_parent_preview": True,
        },
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.presentation.view_mode == "overlay"
    assert c.presentation.merge_to_parent_preview is True
    assert c.merge_executed is False
    assert c.twin_written is False
    assert c.pack_ready is True
    assert any("merge_to_parent_preview=true" in n for n in c.notes)


def test_require_operator_ack_type():
    with pytest.raises(
        RecursiveTwinPresentationCompetitionDrSourceAttachComposeError
    ):
        compose_recursive_twin_presentation_competition_dr_source_attach(
            twin=TWIN,
            presentation=PRESENTATION,
            competition_pack=COMPETITION_PACK,
            operator_ack="yes",  # type: ignore[arg-type]
        )


def test_invalid_view_mode():
    with pytest.raises(
        RecursiveTwinPresentationCompetitionDrSourceAttachComposeError
    ):
        compose_recursive_twin_presentation_competition_dr_source_attach(
            twin=TWIN,
            presentation={**PRESENTATION, "view_mode": "popup"},
            competition_pack=COMPETITION_PACK,
            operator_ack=True,
        )
