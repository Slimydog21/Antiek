"""Tests for the frozen Read sprint-lock."""

from __future__ import annotations

import pytest

from substrate.contracts import read_sprint_lock as lock
from substrate.coordination.roadmap import build_roadmap


def test_all_read_sprints_resolve() -> None:
    for n in range(1, 10):
        d = lock.resolve_read_sprint(n)
        assert d.sprint == n
        assert d.slug and d.deliverable


def test_out_of_range_raises() -> None:
    with pytest.raises(KeyError, match="not in the frozen sprint-lock"):
        lock.resolve_read_sprint(99)


def test_read_sprint_1_servable_corpus_gate_is_live() -> None:
    assert lock.resolve_read_sprint(1).slug == "book-asset-and-corpus-gate"
    assert lock.resolve_read_sprint(1).status == "live"


def test_read_sprint_2_library_browse_is_live() -> None:
    assert lock.resolve_read_sprint(2).slug == "library-browse"
    assert lock.resolve_read_sprint(2).status == "live"


def test_read_sprint_3_book_reader_is_live() -> None:
    assert lock.resolve_read_sprint(3).slug == "book-reader"
    assert lock.resolve_read_sprint(3).status == "live"


def test_read_sprint_4_prompt_to_curate_is_live() -> None:
    assert lock.resolve_read_sprint(4).slug == "prompt-to-curate"
    assert lock.resolve_read_sprint(4).status == "live"


def test_read_sprint_5_ad_border_inventory_is_live() -> None:
    assert lock.resolve_read_sprint(5).slug == "ad-border-inventory"
    assert lock.resolve_read_sprint(5).status == "live"


def test_read_sprint_6_voice_notes_is_live() -> None:
    assert lock.resolve_read_sprint(6).slug == "voice-notes"
    assert lock.resolve_read_sprint(6).status == "live"


def test_read_sprint_7_conversational_rabbit_hole_is_live() -> None:
    assert lock.resolve_read_sprint(7).slug == "conversational-rabbit-hole"
    assert lock.resolve_read_sprint(7).status == "live"


def test_read_sprint_8_research_from_passage_is_live() -> None:
    assert lock.resolve_read_sprint(8).slug == "research-from-passage"
    assert lock.resolve_read_sprint(8).status == "live"


def test_read_sprint_9_ad_revenue_escrow_is_live() -> None:
    assert lock.resolve_read_sprint(9).slug == "ad-revenue-escrow"
    assert lock.resolve_read_sprint(9).status == "live"


def test_all_read_sprints_are_live() -> None:
    assert {lock.resolve_read_sprint(n).status for n in range(1, 10)} == {"live"}


def test_roadmap_consumes_read_sprint_status_and_focus_advances() -> None:
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    assert by_id["read:1"].status.value == "live"
    assert by_id["read:2"].status.value == "live"
    assert by_id["read:3"].status.value == "live"
    assert by_id["read:4"].status.value == "live"
    assert by_id["read:5"].status.value == "live"
    assert by_id["read:6"].status.value == "live"
    assert by_id["read:7"].status.value == "live"
    assert by_id["read:8"].status.value == "live"
    assert by_id["read:9"].status.value == "live"
    assert roadmap.execution_focus() is not None
    assert roadmap.execution_focus().node_id == "speak:9"


def test_read_lock_version_present() -> None:
    assert isinstance(lock.READ_LOCK_VERSION, int) and lock.READ_LOCK_VERSION >= 9
