"""trajectory_read: the same rows trajectory() returns, and whether every stored record was read.

trajectory() skips a record it cannot parse and returns [] for an
investigation with no stored events. That suits a reader that wants what
survives. A gate cannot tell "stood on nothing" from "stood on something we can
no longer read", so trajectory_read reports which one it saw, in the same pass
that reads the rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.event_log import (
    TrajectoryRead,
    log_event,
    seal_investigation,
    trajectory,
    trajectory_read,
)
from substrate.schemas.events import ActionType


def _log(inv: str, events: Path, n: int = 2) -> None:
    for i in range(n):
        log_event(inv, ActionType.INVESTIGATION_COMPLETED,
                  payload={"thesis_summary": f"s{i}"}, events_dir=str(events))


def test_a_fully_readable_trajectory_is_complete_with_trajectorys_rows(tmp_path):
    _log("inv-ok", tmp_path)
    read = trajectory_read("inv-ok", events_dir=str(tmp_path))
    assert isinstance(read, TrajectoryRead)
    assert read.complete is True
    assert read.rows == trajectory("inv-ok", events_dir=str(tmp_path))
    assert len(read.rows) == 2


def test_blank_lines_are_not_unread_records(tmp_path):
    _log("inv-blank", tmp_path)
    with (tmp_path / "inv-blank.jsonl").open("a") as f:
        f.write("\n   \n")
    assert trajectory_read("inv-blank", events_dir=str(tmp_path)).complete is True


def test_no_stored_events_is_not_complete(tmp_path):
    assert trajectory_read("inv-none", events_dir=str(tmp_path)) == TrajectoryRead([], False)


@pytest.mark.parametrize("bad", ["{torn record", "[1, 2]", '"a string"'])
def test_a_record_that_does_not_read_as_an_event_is_not_complete(tmp_path, bad):
    _log("inv-bad", tmp_path)
    with (tmp_path / "inv-bad.jsonl").open("a") as f:
        f.write(bad + "\n")
    _log("inv-bad", tmp_path, n=1)
    read = trajectory_read("inv-bad", events_dir=str(tmp_path))
    assert read.complete is False
    # The readable records are still returned, exactly as trajectory() does.
    assert read.rows == trajectory("inv-bad", events_dir=str(tmp_path))
    assert len(read.rows) == 3


@pytest.mark.parametrize("unsafe", ["{abs}", "../outside/decoy", "a/b", "", ".hidden"])
def test_an_id_that_is_not_an_event_storage_name_is_never_read(tmp_path, unsafe):
    events = tmp_path / "events"
    events.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _log("decoy", outside)
    iid = unsafe.format(abs=str(outside / "decoy"))
    read = trajectory_read(iid, events_dir=str(events))
    assert read == TrajectoryRead([], False)


def test_a_sealed_snapshot_with_a_live_tail_is_complete(tmp_path):
    pytest.importorskip("pyarrow")
    _log("inv-sealed", tmp_path)
    assert seal_investigation("inv-sealed", events_dir=str(tmp_path), outbox_db_path=None)
    _log("inv-sealed", tmp_path, n=1)
    read = trajectory_read("inv-sealed", events_dir=str(tmp_path))
    assert read.complete is True
    assert len(read.rows) == 3
    assert read.rows == trajectory("inv-sealed", events_dir=str(tmp_path))


def test_trajectory_rows_are_unchanged_for_a_readable_log(tmp_path):
    # trajectory() is now a view of the same read: same rows, same order,
    # payloads decoded, for every caller that does not ask about completeness.
    _log("inv-same", tmp_path, n=3)
    raw = [json.loads(line) for line in (tmp_path / "inv-same.jsonl").read_text().splitlines()]
    rows = trajectory("inv-same", events_dir=str(tmp_path))
    assert [r["event_id"] for r in rows] == [r["event_id"] for r in raw]
