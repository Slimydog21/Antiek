"""Hermetic tests for workstation recursive record pack."""

from __future__ import annotations

import pytest

from substrate.workstation_recursive_record_pack import (
    WorkstationRecursiveRecordPackError,
    compose_workstation_recursive_record_pack,
)


def test_packs_without_persist_or_inject() -> None:
    p = compose_workstation_recursive_record_pack(
        session_id="sess-1",
        items=[
            {
                "record_id": "r1",
                "kind": "insight",
                "text": "scaling holds under noise",
                "weight": 0.9,
            },
            {
                "record_id": "r2",
                "kind": "question",
                "text": "what about multimodal?",
                "asset_id": "a1",
                "weight": 0.5,
            },
        ],
    )
    assert p.record_persisted is False
    assert p.prompts_injected is False
    assert p.to_dict()["record_persisted"] is False
    assert p.to_dict()["prompts_injected"] is False
    assert p.pack_ready is True
    assert p.item_count == 2
    assert p.by_kind["insight"] == 1
    assert "scaling holds" in p.prompt_context_lines[0]
    assert p.authority == "workstation_recursive_record_pack_advisory"


def test_empty_no_invent() -> None:
    p = compose_workstation_recursive_record_pack(session_id="s", items=[])
    assert p.pack_ready is False
    assert p.prompt_context_lines == ()
    assert any("no invent" in n for n in p.notes)


def test_max_and_duplicates() -> None:
    p = compose_workstation_recursive_record_pack(
        session_id="s",
        max_context_lines=1,
        items=[
            {
                "record_id": "a",
                "kind": "insight",
                "text": "first",
                "weight": 0.2,
            },
            {
                "record_id": "b",
                "kind": "finding",
                "text": "second",
                "weight": 0.9,
            },
        ],
    )
    assert len(p.prompt_context_lines) == 1
    assert "second" in p.prompt_context_lines[0]
    with pytest.raises(WorkstationRecursiveRecordPackError, match="duplicate"):
        compose_workstation_recursive_record_pack(
            session_id="s",
            items=[
                {"record_id": "x", "kind": "insight", "text": "a"},
                {"record_id": "x", "kind": "question", "text": "b"},
            ],
        )


def test_rejects_invalid_kind() -> None:
    with pytest.raises(WorkstationRecursiveRecordPackError, match="kind"):
        compose_workstation_recursive_record_pack(
            session_id="s",
            items=[{"record_id": "r", "kind": "bogus", "text": "x"}],
        )
