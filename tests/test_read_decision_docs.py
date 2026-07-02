"""Consistency checks for historical Read decision documentation."""

from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]

READ_COMMANDS = {
    "./scripts/canonical_verify.sh read-library",
    "./scripts/canonical_verify.sh read-reader",
    "./scripts/canonical_verify.sh read-curate",
    "./scripts/canonical_verify.sh read-ad-border",
    "./scripts/canonical_verify.sh read-voice-notes",
    "./scripts/canonical_verify.sh read-passage-research",
    "./scripts/canonical_verify.sh read-rabbit-hole",
}


def test_historical_read_backend_blocker_is_marked_superseded() -> None:
    text = (
        REPO / "docs" / "decisions" / "read-backend-sprints-and-drw-frontend-blocker.md"
    ).read_text(encoding="utf-8")
    compact_text = " ".join(text.split())

    assert "Historical decision memo" in text
    assert "2026-07 current state" in text
    assert "blocker superseded" in text
    assert "React surface does not exist" in text
    assert "They are no longer" in compact_text
    assert "`/read/:documentId`" in text
    assert "`apps/reading/src/modes/Reading/TalkToBook.tsx`" in text
    for command in READ_COMMANDS:
        assert command in text


def test_historical_read_frontend_memo_uses_canonical_closure_commands() -> None:
    text = (
        REPO / "docs" / "decisions" / "read-frontend-sprints-on-existing-surface.md"
    ).read_text(encoding="utf-8")
    compact_text = " ".join(text.split())

    assert "Historical implementation memo" in text
    assert "2026-07 current proof" in text
    assert "Do not use the historical per-file test counts" in compact_text
    assert "one-reader route" in text
    assert "`/read/:documentId`" in text
    assert "platform matrix remains the source of truth" in compact_text
    for command in READ_COMMANDS:
        assert command in text
