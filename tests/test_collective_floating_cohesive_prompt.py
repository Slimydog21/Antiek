"""Hermetic tests for pure collective floating cohesive prompt."""

from __future__ import annotations

import pytest

from substrate.collective_floating_cohesive_prompt import (
    CollectiveFloatingCohesivePromptError,
    build_collective_floating_cohesive_prompt,
)


BASE = [
    {
        "instance_id": "fdr_1",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "highlight": "scaling laws",
        "context": ["arxiv:1234 finding"],
    },
    {
        "instance_id": "fdr_2",
        "parent_asset_id": "asset-1",
        "status": "open",
        "prior_prompt": "contrast substack claims",
    },
]


def test_builds_without_live_dispatch() -> None:
    intent = build_collective_floating_cohesive_prompt(
        BASE,
        cohesive_prompt="Synthesize both lanes",
        operator_ack=True,
    )
    assert intent.live_dispatched is False
    assert intent.to_dict()["live_dispatched"] is False
    assert intent.pack_ready is True
    assert intent.member_count == 2
    assert intent.instance_ids == ("fdr_1", "fdr_2")
    assert len(intent.context_cards) >= 2
    assert intent.authority == "collective_floating_cohesive_prompt_advisory"


def test_pack_ready_false_without_ack() -> None:
    intent = build_collective_floating_cohesive_prompt(
        BASE,
        cohesive_prompt="Continue as one unit",
        operator_ack=False,
    )
    assert intent.pack_ready is False
    assert intent.live_dispatched is False
    assert any("pack_ready=false" in n for n in intent.notes)


def test_requires_two_same_parent_distinct() -> None:
    with pytest.raises(CollectiveFloatingCohesivePromptError, match="at least 2"):
        build_collective_floating_cohesive_prompt(
            [BASE[0]],
            cohesive_prompt="x",
            operator_ack=False,
        )
    with pytest.raises(CollectiveFloatingCohesivePromptError, match="same parent"):
        build_collective_floating_cohesive_prompt(
            [BASE[0], {**BASE[1], "parent_asset_id": "other"}],
            cohesive_prompt="x",
            operator_ack=False,
        )
    with pytest.raises(CollectiveFloatingCohesivePromptError, match="distinct"):
        build_collective_floating_cohesive_prompt(
            [BASE[0], {**BASE[0]}],
            cohesive_prompt="x",
            operator_ack=False,
        )


def test_rejects_closed_and_blank_prompt() -> None:
    with pytest.raises(CollectiveFloatingCohesivePromptError, match="not closed"):
        build_collective_floating_cohesive_prompt(
            [BASE[0], {**BASE[1], "status": "closed"}],
            cohesive_prompt="ok",
            operator_ack=False,
        )
    with pytest.raises(CollectiveFloatingCohesivePromptError, match="cohesive_prompt"):
        build_collective_floating_cohesive_prompt(
            BASE,
            cohesive_prompt="   ",
            operator_ack=False,
        )


def test_never_invents_context() -> None:
    intent = build_collective_floating_cohesive_prompt(
        [
            {
                "instance_id": "a",
                "parent_asset_id": "p",
                "status": "completed",
            },
            {
                "instance_id": "b",
                "parent_asset_id": "p",
                "status": "completed",
            },
        ],
        cohesive_prompt="Ask both agents the same critique",
        operator_ack=True,
    )
    assert intent.context_cards == ()
    assert any("no invent content" in n for n in intent.notes)
    assert intent.live_dispatched is False


def test_extra_context() -> None:
    intent = build_collective_floating_cohesive_prompt(
        BASE,
        cohesive_prompt="Cross-examine",
        operator_ack=True,
        extra_context=["operator note: prioritize citations"],
    )
    assert "operator note: prioritize citations" in intent.context_cards
    assert intent.live_dispatched is False
