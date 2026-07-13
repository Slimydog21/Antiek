from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from substrate.event_log import (
    append_event_once,
    log_event,
    prepare_typed_event,
    seal_investigation,
    trajectory,
)
from substrate.schemas.events import GraphNodeInsertedPayload


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
    parquet.read_table = lambda path: FakeTable(json.loads(Path(path).read_text(encoding="utf-8")))
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
    parquet.read_table = lambda path: FakeTable(json.loads(Path(path).read_text(encoding="utf-8")))
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


@pytest.mark.parametrize("matching_last", [False, True])
def test_seal_refuses_conflicting_duplicate_envelopes(tmp_path, monkeypatch, matching_last):
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
    parquet.read_table = lambda path: FakeTable(json.loads(Path(path).read_text(encoding="utf-8")))
    monkeypatch.setitem(sys.modules, "pyarrow", arrow)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", parquet)
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)

    matching = prepare_typed_event(
        "inv-conflict",
        GraphNodeInsertedPayload(
            node_id="node-conflict",
            canonical_label="matching",
            node_type="claim",
            graph_scope="depth",
            has_embedding=False,
        ),
        event_id="event-conflict",
    )
    conflicting = matching.model_copy(
        update={
            "payload": GraphNodeInsertedPayload(
                node_id="node-conflict",
                canonical_label="conflicting",
                node_type="claim",
                graph_scope="depth",
                has_embedding=False,
            )
        }
    )
    first, second = (conflicting, matching) if matching_last else (matching, conflicting)
    append_event_once(first, events_dir=str(tmp_path))
    event_path = next(tmp_path.glob("*.jsonl"))
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(second.model_dump(mode="json"), default=str) + "\n")

    with pytest.raises(ValueError, match="event id collision"):
        seal_investigation("inv-conflict", events_dir=str(tmp_path))
    assert event_path.exists()
    assert not next(tmp_path.glob("*.parquet"), None)
