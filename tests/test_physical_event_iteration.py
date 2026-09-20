from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from substrate.event_log import (
    PhysicalTrajectoryError,
    iter_physical_events,
    physical_event_sha256,
    read_physical_event_page,
)
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
        "evt-first",
        "evt-third",
    ]


def test_page_observation_carries_identity_cursor_and_source(tmp_path: Path) -> None:
    events = tmp_path / "events"
    events.mkdir()
    rows = [_event("evt-1", "one", "2020"), _event("evt-2", "two", "2021")]
    _write_tail(events / "inv-1.jsonl", rows)

    page = read_physical_event_page("inv-1", limit=1, events_dir=str(events))
    observation = page.observations[0]
    assert observation.normalized_sha256 == physical_event_sha256(rows[0])
    assert observation.source_kind == "tail"
    assert observation.cursor_before.jsonl_byte_offset == 0
    assert observation.cursor_after.jsonl_byte_offset > 0


def test_large_tail_cursor_seeks_directly_on_second_page(
    monkeypatch, tmp_path: Path
) -> None:
    events = tmp_path / "events"
    events.mkdir()
    rows = [_event(f"evt-{index}", str(index), "2020") for index in range(1_002)]
    _write_tail(events / "inv-1.jsonl", rows)
    first = read_physical_event_page(
        "inv-1", limit=1_001, scan_limit=1_001, events_dir=str(events)
    )
    calls = 0
    original = events_module.json.loads

    def counted_loads(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(events_module.json, "loads", counted_loads)
    second = read_physical_event_page(
        "inv-1",
        storage_cursor=first.cursors[-1],
        limit=1,
        events_dir=str(events),
    )

    assert [row["event_id"] for row in second.events] == ["evt-1001"]
    assert calls == 1


def test_tail_cursor_tampering_and_expired_deadline_fail_closed(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events"
    events.mkdir()
    _write_tail(events / "inv-1.jsonl", [_event("evt-1", "one", "2020")])
    first = read_physical_event_page("inv-1", events_dir=str(events))
    cursor = first.cursors[-1]

    with pytest.raises(PhysicalTrajectoryError, match="beyond EOF"):
        read_physical_event_page(
            "inv-1",
            storage_cursor=events_module.PhysicalStorageCursor(
                cursor.snapshot_generation,
                cursor.snapshot_row_count,
                cursor.next_snapshot_row_offset,
                cursor.jsonl_byte_offset + 1,
            ),
            events_dir=str(events),
        )
    expired = read_physical_event_page(
        "inv-1", deadline=time.monotonic() - 1, events_dir=str(events)
    )
    assert expired.events == ()
    assert expired.scanned == 0
    assert expired.has_more


def test_tail_cursor_must_be_at_newline_boundary(tmp_path: Path) -> None:
    events = tmp_path / "events"
    events.mkdir()
    _write_tail(events / "inv-1.jsonl", [_event("evt-1", "one", "2020")])

    with pytest.raises(PhysicalTrajectoryError, match="record boundary"):
        read_physical_event_page(
            "inv-1",
            storage_cursor=events_module.PhysicalStorageCursor(None, 0, 0, 2),
            events_dir=str(events),
        )


def test_page_returns_identical_and_conflicting_physical_duplicates(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events"
    events.mkdir()
    first = _event("evt-1", "one", "2020")
    second = _event("evt-2", "two", "2021")
    _write_tail(events / "inv-1.jsonl", [first, first, second])

    page = read_physical_event_page("inv-1", events_dir=str(events))
    assert [row["event_id"] for row in page.events] == ["evt-1", "evt-1", "evt-2"]

    _write_tail(
        events / "inv-1.jsonl",
        [first, {**first, "payload": {"note_text": "changed"}}],
    )
    conflict = read_physical_event_page("inv-1", events_dir=str(events))
    assert len(conflict.observations) == 2
    assert conflict.observations[0].normalized_sha256 != conflict.observations[1].normalized_sha256


def test_page_resumes_across_seal_and_reseal(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    events = tmp_path / "events"
    events.mkdir()
    rows = [_event(f"evt-{index}", str(index), "2020") for index in range(4)]
    _write_tail(events / "inv-1.jsonl", rows[:2])
    first = read_physical_event_page("inv-1", limit=1, events_dir=str(events))
    events_module.seal_investigation("inv-1", events_dir=str(events))
    _write_tail(events / "inv-1.jsonl", rows[2:])
    second = read_physical_event_page(
        "inv-1",
        storage_cursor=first.cursors[-1],
        limit=2,
        events_dir=str(events),
    )
    events_module.seal_investigation("inv-1", events_dir=str(events))
    third = read_physical_event_page(
        "inv-1",
        storage_cursor=second.cursors[-1],
        limit=2,
        events_dir=str(events),
    )

    assert [row["event_id"] for row in second.events] == ["evt-0", "evt-1"]
    assert [row["event_id"] for row in third.events] == ["evt-0", "evt-1"]


def test_page_skips_parquet_payload_row_groups(monkeypatch, tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    events = tmp_path / "events"
    events.mkdir()
    rows = [_event(f"evt-{index}", "x" * 1000, "2020") for index in range(50)]
    pq.write_table(
        pa.Table.from_pylist(rows), events / "inv-1.parquet", row_group_size=10
    )
    original = pq.ParquetFile
    payload_groups: list[int] = []

    class InstrumentedParquetFile:
        def __init__(self, *args, **kwargs):
            self._inner = original(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def read_row_group(self, group, columns=None):
            payload_groups.append(group)
            return self._inner.read_row_group(group, columns=columns)

        def iter_batches(self, *args, row_groups=None, **kwargs):
            payload_groups.extend(row_groups or [])
            return self._inner.iter_batches(*args, row_groups=row_groups, **kwargs)

    monkeypatch.setattr(pq, "ParquetFile", InstrumentedParquetFile)
    initial = read_physical_event_page("inv-1", limit=40, events_dir=str(events))
    payload_groups.clear()
    page = read_physical_event_page("inv-1", storage_cursor=initial.cursors[-1],
                                    limit=2, events_dir=str(events))

    assert [row["event_id"] for row in page.events] == ["evt-40", "evt-41"]
    assert set(payload_groups) == {4}


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


def test_physical_reader_returns_conflicting_identity(tmp_path: Path) -> None:
    events = tmp_path / "events"
    events.mkdir()
    _write_tail(
        events / "inv-1.jsonl",
        [
            _event("evt-same", "first bytes", "2020"),
            _event("evt-same", "different bytes", "2020"),
        ],
    )

    assert len(list(iter_physical_events("inv-1", events_dir=str(events)))) == 2


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


def test_physical_reader_streams_under_lock_and_releases_on_close(
    monkeypatch, tmp_path: Path
) -> None:
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
    assert held
    rows.close()
    assert not held
