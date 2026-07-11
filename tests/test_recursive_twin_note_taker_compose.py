"""Pure tests for recursive twin note-taker compose."""

from __future__ import annotations

import pytest

from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)


def test_propose_without_write():
    c = compose_recursive_twin_note_taker(
        parent_asset_id="asset-1",
        source_excerpt="<p>Scaling laws under noise</p>",
        operator_ack=True,
        focus_questions=["What is the sample size?"],
    )
    assert c.twin_propose_ready is True
    assert c.twin_written is False
    assert c.prompts_injected is False
    assert c.live_dispatch_authorized is False
    assert c.focus_question_count == 1
    assert len(c.twin_scaffold_sections) >= 4
    assert c.to_dict()["twin_written"] is False


def test_not_ready_and_blank():
    no_ack = compose_recursive_twin_note_taker(
        parent_asset_id="a",
        source_excerpt="body",
        operator_ack=False,
    )
    assert no_ack.twin_propose_ready is False
    with pytest.raises(RecursiveTwinNoteTakerComposeError, match="source_excerpt"):
        compose_recursive_twin_note_taker(
            parent_asset_id="a",
            source_excerpt="  ",
            operator_ack=True,
        )
