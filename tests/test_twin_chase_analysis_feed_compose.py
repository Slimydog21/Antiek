"""Pure tests for twin chase analysis feed compose."""

from __future__ import annotations

import pytest

from substrate.twin_chase_analysis_feed_compose import (
    TwinChaseAnalysisFeedComposeError,
    compose_twin_chase_analysis_feed,
    format_twin_chase_analysis_feed_summary,
)


def test_feed_ready():
    c = compose_twin_chase_analysis_feed(
        session_id="sess-1",
        parent_asset_id="paper-1",
        findings=[
            {
                "source_id": "chase_1",
                "body": "scaling holds under noise",
                "kind": "insight",
            },
            {
                "source_id": "chase_2",
                "body": "What is the failure mode?",
                "kind": "question",
            },
        ],
        analysis_excerpt="draft collective analysis scaffold",
        operator_ack=True,
        mark_for_prompt_context=True,
    )
    assert c.feed_ready is True
    assert c.finding_count == 2
    assert c.insight_count == 1
    assert c.question_count == 1
    assert c.twin_written is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_dispatch_authorized is False
    s = format_twin_chase_analysis_feed_summary(c)
    assert "twin_written=false" in s
    assert c.to_dict()["twin_written"] is False


def test_ack_false():
    c = compose_twin_chase_analysis_feed(
        session_id="s",
        parent_asset_id="p",
        findings=[{"source_id": "a", "body": "x", "kind": "insight"}],
        operator_ack=False,
    )
    assert c.feed_ready is False
    assert c.twin_written is False


def test_empty_findings():
    with pytest.raises(TwinChaseAnalysisFeedComposeError, match="non-empty"):
        compose_twin_chase_analysis_feed(
            session_id="s",
            parent_asset_id="p",
            findings=[],
            operator_ack=True,
        )


def test_duplicate_source():
    with pytest.raises(TwinChaseAnalysisFeedComposeError, match="duplicate"):
        compose_twin_chase_analysis_feed(
            session_id="s",
            parent_asset_id="p",
            findings=[
                {"source_id": "a", "body": "1"},
                {"source_id": "a", "body": "2"},
            ],
            operator_ack=True,
        )
