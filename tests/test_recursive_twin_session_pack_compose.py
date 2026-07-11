"""Hermetic tests for recursive twin session pack compose."""

from __future__ import annotations

import pytest

from substrate.recursive_twin_session_pack_compose import (
    RecursiveTwinSessionPackComposeError,
    compose_recursive_twin_session_pack,
)


def test_pack_ready_without_store_mutation() -> None:
    p = compose_recursive_twin_session_pack(
        session_id="sess-1",
        members=[
            {
                "asset_id": "a1",
                "twin_bound": True,
                "insights": ["scaling holds under noise"],
                "questions": ["what about multimodal?"],
            },
            {
                "asset_id": "a2",
                "twin_bound": False,
                "insights": [],
                "questions": [],
            },
        ],
    )
    assert p.twin_store_mutated is False
    assert p.to_dict()["twin_store_mutated"] is False
    assert p.pack_ready is True
    assert p.insight_count == 1
    assert p.question_count == 1
    assert p.bound_count == 1
    assert p.unbound_count == 1
    assert p.authority == "recursive_twin_session_pack_compose_advisory"


def test_not_ready_without_bound_or_content() -> None:
    unbound = compose_recursive_twin_session_pack(
        session_id="s",
        members=[
            {
                "asset_id": "a1",
                "twin_bound": False,
                "insights": ["x"],
                "questions": [],
            }
        ],
    )
    assert unbound.pack_ready is False
    assert unbound.twin_store_mutated is False

    empty = compose_recursive_twin_session_pack(
        session_id="s",
        members=[
            {
                "asset_id": "a1",
                "twin_bound": True,
                "insights": [],
                "questions": [],
            }
        ],
    )
    assert empty.pack_ready is False
    assert any("no invent" in n for n in empty.notes)


def test_rejects_duplicates_and_blank() -> None:
    with pytest.raises(RecursiveTwinSessionPackComposeError, match="duplicate"):
        compose_recursive_twin_session_pack(
            session_id="s",
            members=[
                {
                    "asset_id": "a1",
                    "twin_bound": True,
                    "insights": [],
                    "questions": [],
                },
                {
                    "asset_id": "a1",
                    "twin_bound": True,
                    "insights": [],
                    "questions": [],
                },
            ],
        )
    with pytest.raises(RecursiveTwinSessionPackComposeError, match="insights"):
        compose_recursive_twin_session_pack(
            session_id="s",
            members=[
                {
                    "asset_id": "a1",
                    "twin_bound": True,
                    "insights": ["  "],
                    "questions": [],
                }
            ],
        )
