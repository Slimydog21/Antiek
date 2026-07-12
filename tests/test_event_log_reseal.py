from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

from substrate.event_log import log_event, seal_investigation, trajectory


def test_reseal_merges_post_seal_live_tail_without_losing_prefix(tmp_path, monkeypatch):
    class FakeTable:
        def __init__(self, rows):
            self.rows = rows

        def to_pylist(self):
            return self.rows

    arrow = ModuleType("pyarrow")
    arrow.Table = type("Table", (), {"from_pylist": staticmethod(FakeTable)})
    parquet = ModuleType("pyarrow.parquet")
    parquet.write_table = lambda table, path, compression=None: Path(path).write_text(
        json.dumps(table.rows), encoding="utf-8"
    )
    parquet.read_table = lambda path: FakeTable(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
    monkeypatch.setitem(sys.modules, "pyarrow", arrow)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", parquet)
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    events_dir = str(tmp_path)

    first = log_event(
        "inv-reseal",
        "test.prefix",
        payload={"sequence": 1},
        events_dir=events_dir,
    )
    assert first
    assert seal_investigation("inv-reseal", events_dir=events_dir)

    second = log_event(
        "inv-reseal",
        "test.tail",
        payload={"sequence": 2},
        events_dir=events_dir,
    )
    assert second
    assert {row["event_id"] for row in trajectory("inv-reseal", events_dir=events_dir)} == {
        first,
        second,
    }

    assert seal_investigation("inv-reseal", events_dir=events_dir)
    rows = trajectory("inv-reseal", events_dir=events_dir)
    assert [row["event_id"] for row in rows] == [first, second]


def test_trajectory_deduplicates_retained_jsonl_after_seal(tmp_path, monkeypatch):
    class FakeTable:
        def __init__(self, rows):
            self.rows = rows

        def to_pylist(self):
            return self.rows

    arrow = ModuleType("pyarrow")
    arrow.Table = type("Table", (), {"from_pylist": staticmethod(FakeTable)})
    parquet = ModuleType("pyarrow.parquet")
    parquet.write_table = lambda table, path, compression=None: Path(path).write_text(
        json.dumps(table.rows), encoding="utf-8"
    )
    parquet.read_table = lambda path: FakeTable(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
    monkeypatch.setitem(sys.modules, "pyarrow", arrow)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", parquet)
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)

    event_id = log_event(
        "inv-retained",
        "test.retained",
        payload={"sequence": 1},
        events_dir=str(tmp_path),
    )
    assert event_id
    assert seal_investigation(
        "inv-retained",
        events_dir=str(tmp_path),
        delete_jsonl=False,
    )
    rows = trajectory("inv-retained", events_dir=str(tmp_path))
    assert [row["event_id"] for row in rows] == [event_id]
