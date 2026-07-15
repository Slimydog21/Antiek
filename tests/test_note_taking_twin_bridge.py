"""Red-proof: note_taker emerged notes bridge into TwinNotesStore."""

from __future__ import annotations

from pathlib import Path

from interfaces.research.api.note_taking import record_emerged_notes_as_twin
from roles.note_taker.parser import ExtractedNote
from substrate.twin_notes.store import TwinNotesStore


def _note(text: str, note_id: str = "n-1") -> ExtractedNote:
    return ExtractedNote(
        note_id=note_id,
        text=text,
        confidence="medium",
        source_event_ids=("e1",),
    )


def test_bridge_records_insights_and_questions(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    twin = record_emerged_notes_as_twin(
        [
            _note("The scaling law still holds", "n-a"),
            _note("What is the sample-efficiency floor?", "n-b"),
        ],
        parent_asset_id="inv-42",
        store=store,
        enabled=True,
    )
    assert twin is not None
    assert twin.parent_asset_id == "inv-42"
    assert twin.insights == ["The scaling law still holds"]
    assert twin.questions == ["What is the sample-efficiency floor?"]
    listed = store.list_for_parent("inv-42")
    assert len(listed) == 1
    assert listed[0].twin_id == twin.twin_id


def test_bridge_disabled_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    store = TwinNotesStore(tmp_path)
    monkeypatch.setenv("ANTIEK_TWIN_NOTES_FROM_NOTE_TAKER", "0")
    twin = record_emerged_notes_as_twin(
        [_note("Should not land")],
        parent_asset_id="inv-x",
        store=store,
        enabled=None,  # consult env
    )
    assert twin is None
    assert store.list_for_parent("inv-x") == []


def test_bridge_empty_notes_noop(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    assert (
        record_emerged_notes_as_twin([], parent_asset_id="p", store=store, enabled=True)
        is None
    )


def test_bridge_explicit_enabled_overrides_env_off(
    tmp_path: Path, monkeypatch
) -> None:
    store = TwinNotesStore(tmp_path)
    monkeypatch.setenv("ANTIEK_TWIN_NOTES_FROM_NOTE_TAKER", "0")
    twin = record_emerged_notes_as_twin(
        [_note("forced on")],
        parent_asset_id="p2",
        store=store,
        enabled=True,
    )
    assert twin is not None
    assert twin.insights == ["forced on"]


def test_bridge_whitespace_only_notes_noop(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    twin = record_emerged_notes_as_twin(
        [_note("   ")],
        parent_asset_id="p3",
        store=store,
        enabled=True,
    )
    assert twin is None
    assert store.list_for_parent("p3") == []


def test_bridge_store_failure_is_swallowed(tmp_path: Path) -> None:
    class BoomStore(TwinNotesStore):
        def record(self, *a, **k):  # type: ignore[no-untyped-def]
            raise OSError("disk full")

    twin = record_emerged_notes_as_twin(
        [_note("still emit path")],
        parent_asset_id="p4",
        store=BoomStore(tmp_path),
        enabled=True,
    )
    assert twin is None