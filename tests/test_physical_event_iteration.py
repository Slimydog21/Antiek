from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from substrate.event_log import PhysicalTrajectoryError, iter_physical_events
from substrate.event_log import events as events_module


def _event(event_id: str, text: str, emitted_at: str) -> dict[str, object]:
    return {
        "event_id": event_id,
        "investigation_id": "inv-1",
        "action_type": "note.emerged",
        "payload": {"note_text": text},
        "emitted_at": emitted_at,
    }


def _write_tail(path: Path, rows: list[dict[str, object]], *, complete: bool = True) -> None:
    data = b"".join(json.dumps(row).encode() + b"\n" for row in rows)
    path.write_bytes(data if complete or not data else data[:-1])


def test_physical_reader_preserves_snapshot_then_tail_order(tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    events = tmp_path / "events"
    events.mkdir()
    first = _event("evt-first", "first", "2030")
    second = _event("evt-second", "second", "2020")
    third = _event("evt-third", "third", "2010")
    pq.write_table(pa.Table.from_pylist([first, second]), events / "inv-1.parquet")
    _write_tail(events / "inv-1.jsonl", [first, third])

    rows = list(iter_physical_events("inv-1", events_dir=str(events)))

    assert [row["event_id"] for row in rows] == [
        "evt-first",
        "evt-second",
        "evt-third",
    ]


def test_seal_preserves_physical_append_order(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    events = tmp_path / "events"
    events.mkdir()
    _write_tail(
        events / "inv-1.jsonl",
        [
            _event("evt-first", "first", "2030"),
            _event("evt-second", "second", "2020"),
        ],
    )

    assert events_module.seal_investigation(
        "inv-1", events_dir=str(events)
    ) is not None
    rows = list(iter_physical_events("inv-1", events_dir=str(events)))

    assert [row["event_id"] for row in rows] == ["evt-first", "evt-second"]


def test_physical_reader_waits_for_complete_tail_and_rejects_completed_poison(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events"
    events.mkdir()
    tail = events / "inv-1.jsonl"
    _write_tail(tail, [_event("evt-1", "one", "2020")], complete=False)
    assert list(iter_physical_events("inv-1", events_dir=str(events))) == []

    tail.write_bytes(b"{not-json}\n")
    with pytest.raises(PhysicalTrajectoryError, match="malformed completed JSONL"):
        list(iter_physical_events("inv-1", events_dir=str(events)))


def test_physical_reader_rejects_conflicting_identity(tmp_path: Path) -> None:
    events = tmp_path / "events"
    events.mkdir()
    _write_tail(
        events / "inv-1.jsonl",
        [
            _event("evt-same", "first bytes", "2020"),
            _event("evt-same", "different bytes", "2020"),
        ],
    )

    with pytest.raises(PhysicalTrajectoryError, match="identity conflicts"):
        list(iter_physical_events("inv-1", events_dir=str(events)))


@pytest.mark.parametrize("link_kind", ["symbolic", "hard"])
def test_physical_reader_rejects_linked_event_files(
    tmp_path: Path, link_kind: str
) -> None:
    events = tmp_path / "events"
    events.mkdir()
    outside = tmp_path / "outside.jsonl"
    _write_tail(outside, [_event("evt-linked", "linked", "2020")])
    target = events / "inv-1.jsonl"
    if link_kind == "symbolic":
        target.symlink_to(outside)
    else:
        os.link(outside, target)

    with pytest.raises(
        PhysicalTrajectoryError, match="event file must be regular and singly linked"
    ):
        list(iter_physical_events("inv-1", events_dir=str(events)))


def test_physical_reader_rejects_linked_event_root(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)

    with pytest.raises(PhysicalTrajectoryError, match="event root must be a real directory"):
        list(iter_physical_events("inv-1", events_dir=str(linked)))


def test_append_and_seal_share_investigation_lock(monkeypatch, tmp_path: Path) -> None:
    lock_depth = 0
    appended: list[dict[str, Any]] = []

    @contextmanager
    def tracking_lock(*args, **kwargs):
        nonlocal lock_depth
        lock_depth += 1
        try:
            yield
        finally:
            lock_depth -= 1

    def guarded_append(path: str, row: dict[str, Any]) -> None:
        assert lock_depth > 0
        appended.append(row)

    def guarded_seal(*args, **kwargs) -> str:
        assert lock_depth > 0
        return "sealed"

    monkeypatch.setattr(events_module, "investigation_event_lock", tracking_lock)
    monkeypatch.setattr(events_module, "_append_jsonl", guarded_append)
    monkeypatch.setattr(events_module, "_seal_investigation_unlocked", guarded_seal)

    event_id = events_module.log_event(
        "inv-1", "note.emerged", events_dir=str(tmp_path)
    )
    assert event_id is not None
    assert appended[0]["event_id"] == event_id
    assert events_module.seal_investigation(
        "inv-1", events_dir=str(tmp_path)
    ) == "sealed"
    assert lock_depth == 0


@pytest.mark.parametrize("link_kind", ["symbolic", "hard"])
def test_append_rejects_linked_event_target(tmp_path: Path, link_kind: str) -> None:
    events = tmp_path / "events"
    events.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text("outside", encoding="utf-8")
    target = events / "inv-1.jsonl"
    if link_kind == "symbolic":
        target.symlink_to(outside)
    else:
        os.link(outside, target)

    with pytest.raises((OSError, PhysicalTrajectoryError)):
        events_module._append_jsonl(target.as_posix(), _event("evt-1", "x", "2020"))
    assert outside.read_text(encoding="utf-8") == "outside"


def test_physical_reader_releases_lock_before_yield(monkeypatch, tmp_path: Path) -> None:
    events = tmp_path / "events"
    events.mkdir()
    _write_tail(events / "inv-1.jsonl", [_event("evt-1", "one", "2020")])
    held = False

    @contextmanager
    def tracking_lock(*args, **kwargs):
        nonlocal held
        held = True
        try:
            yield
        finally:
            held = False

    monkeypatch.setattr(events_module, "investigation_event_lock", tracking_lock)
    rows = iter_physical_events("inv-1", events_dir=str(events))

    assert next(rows)["event_id"] == "evt-1"
    assert not held
