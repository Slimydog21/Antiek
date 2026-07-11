"""Pure tests for write-mode twin draft merge compose."""

from __future__ import annotations

import pytest

from substrate.write_mode_twin_draft_merge_compose import (
    WriteModeTwinDraftMergeComposeError,
    compose_write_mode_twin_draft_merge,
)


def test_builds_provisional_draft():
    c = compose_write_mode_twin_draft_merge(
        draft_id="draft-1",
        base_draft_html="<p>Opening argument</p>",
        operator_ack=True,
        slices=[
            {
                "parent_asset_id": "a1",
                "insights": ["claim holds under noise"],
                "questions": ["sample size?"],
            },
            {
                "parent_asset_id": "a2",
                "insights": ["routing is non-linear"],
                "questions": [],
            },
        ],
    )
    assert c.draft_ready is True
    assert c.section_count >= 4
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.store_mutated is False
    assert c.to_dict()["draft_written"] is False


def test_not_ready_paths():
    no_ack = compose_write_mode_twin_draft_merge(
        draft_id="d",
        operator_ack=False,
        slices=[
            {"parent_asset_id": "a", "insights": ["x"], "questions": []},
        ],
    )
    assert no_ack.draft_ready is False
    empty = compose_write_mode_twin_draft_merge(
        draft_id="d",
        operator_ack=True,
        slices=[{"parent_asset_id": "a", "insights": [], "questions": []}],
    )
    assert empty.draft_ready is False


def test_rejects_empty_and_duplicate():
    with pytest.raises(WriteModeTwinDraftMergeComposeError, match="slices"):
        compose_write_mode_twin_draft_merge(
            draft_id="d", operator_ack=True, slices=[]
        )
    with pytest.raises(WriteModeTwinDraftMergeComposeError, match="duplicate"):
        compose_write_mode_twin_draft_merge(
            draft_id="d",
            operator_ack=True,
            slices=[
                {"parent_asset_id": "a", "insights": ["x"], "questions": []},
                {"parent_asset_id": "a", "insights": ["y"], "questions": []},
            ],
        )
