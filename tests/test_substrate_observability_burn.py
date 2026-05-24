"""Tests for substrate/observability/burn — recorder, decorator, context, CLI."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from substrate.observability.burn import BurnEvent, BurnRecorder
from substrate.observability.burn_context import (
    BurnContext, BurnContextNotSet,
    current_burn_context, reset_burn_context, set_burn_context,
)
from substrate.observability.burn_decorator import _extract_usage, track_burn


@pytest.fixture(autouse=True)
def _reset_recorder_cache():
    BurnRecorder._reset_instances()
    yield
    BurnRecorder._reset_instances()


@pytest.fixture
def recorder(tmp_path: Path) -> BurnRecorder:
    return BurnRecorder.for_project(tmp_path)


def test_schema_applied_on_first_connection(recorder: BurnRecorder) -> None:
    conn = sqlite3.connect(str(recorder.db_path))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "burn_events" in tables


def test_indexes_exist(recorder: BurnRecorder) -> None:
    conn = sqlite3.connect(str(recorder.db_path))
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_burn_ts", "idx_burn_session_ts", "idx_burn_project_ts", "idx_burn_tool_ts"} <= indexes


def test_wal_mode_active(recorder: BurnRecorder) -> None:
    recorder.record(BurnEvent(session_id="s", call_id="c", model="m", input_tokens=1, output_tokens=1))
    conn = sqlite3.connect(str(recorder.db_path))
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_record_inserts_one_row(recorder: BurnRecorder) -> None:
    recorder.record(
        BurnEvent(
            session_id="sess-1", call_id="call-1", model="claude-opus-4",
            input_tokens=100, output_tokens=50, cached_tokens=20,
            tool_id="primary_llm", project_id="proj-a",
            extension_ids_active=("project:foo",),
        )
    )
    rows = recorder.query("SELECT * FROM burn_events")
    assert len(rows) == 1
    assert json.loads(rows[0]["extension_ids_active"]) == ["project:foo"]


def test_record_many_in_one_transaction(recorder: BurnRecorder) -> None:
    events = [
        BurnEvent(session_id="s", call_id=f"c{i}", model="m", input_tokens=i, output_tokens=i)
        for i in range(10)
    ]
    recorder.record_many(events)
    assert recorder.query("SELECT COUNT(*) AS n FROM burn_events")[0]["n"] == 10


def test_kill_switch_disables_record(monkeypatch: pytest.MonkeyPatch, recorder: BurnRecorder) -> None:
    monkeypatch.setenv("ANTIEK_DISABLE_BURN_TELEMETRY", "1")
    recorder.record(BurnEvent(session_id="s", call_id="c", model="m", input_tokens=1, output_tokens=1))
    assert recorder.query("SELECT COUNT(*) AS n FROM burn_events")[0]["n"] == 0


def test_current_burn_context_raises_when_unset() -> None:
    with pytest.raises(BurnContextNotSet):
        current_burn_context()


def test_burn_context_set_reset(tmp_path: Path) -> None:
    ctx = BurnContext(session_id="s1", project_root=tmp_path)
    token = set_burn_context(ctx)
    try:
        assert current_burn_context() is ctx
    finally:
        reset_burn_context(token)
    with pytest.raises(BurnContextNotSet):
        current_burn_context()


def test_extract_usage_anthropic_shape() -> None:
    msg = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=120, output_tokens=80, cache_read_input_tokens=10),
        model="claude-opus-4-7",
    )
    assert _extract_usage(msg) == {
        "input_tokens": 120, "output_tokens": 80, "cached_tokens": 10, "model": "claude-opus-4-7",
    }


def test_extract_usage_openai_shape() -> None:
    msg = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=200, completion_tokens=50), model="gpt-4o")
    assert _extract_usage(msg) == {
        "input_tokens": 200, "output_tokens": 50, "cached_tokens": 0, "model": "gpt-4o",
    }


def test_extract_usage_dict_shape() -> None:
    msg = {"model": "local-llama",
           "usage": {"input_tokens": 33, "output_tokens": 7, "cache_read_input_tokens": 2}}
    assert _extract_usage(msg) == {
        "input_tokens": 33, "output_tokens": 7, "cached_tokens": 2, "model": "local-llama",
    }


def test_track_burn_records_on_success(tmp_path: Path) -> None:
    ctx = BurnContext(session_id="s1", project_root=tmp_path, project_id="p1")
    token = set_burn_context(ctx)
    try:
        @track_burn(tool_id="primary_llm")
        def call_model():
            return SimpleNamespace(
                usage=SimpleNamespace(input_tokens=42, output_tokens=7), model="claude-opus-4-7",
            )
        call_model()
        recorder = BurnRecorder.for_project(tmp_path)
        rows = recorder.query("SELECT * FROM burn_events")
        assert len(rows) == 1
        assert rows[0]["input_tokens"] == 42
    finally:
        reset_burn_context(token)


def test_track_burn_records_on_exception_and_re_raises(tmp_path: Path) -> None:
    ctx = BurnContext(session_id="s1", project_root=tmp_path)
    token = set_burn_context(ctx)
    try:
        @track_burn(tool_id="primary_llm")
        def call_model() -> None:
            raise RuntimeError("simulated provider error")
        with pytest.raises(RuntimeError, match="simulated provider error"):
            call_model()
        recorder = BurnRecorder.for_project(tmp_path)
        rows = recorder.query("SELECT * FROM burn_events")
        assert len(rows) == 1
        assert "simulated provider error" in (rows[0]["error"] or "")
    finally:
        reset_burn_context(token)


def test_cli_report_aggregates_by_tool(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from substrate.observability.burn_cli import main
    recorder = BurnRecorder.for_project(tmp_path)
    recorder.record_many([
        BurnEvent(session_id="s", call_id="c1", model="m", input_tokens=10, output_tokens=5, tool_id="A"),
        BurnEvent(session_id="s", call_id="c2", model="m", input_tokens=20, output_tokens=5, tool_id="A"),
        BurnEvent(session_id="s", call_id="c3", model="m", input_tokens=5, output_tokens=5, tool_id="B"),
    ])
    rc = main(["--project-root", str(tmp_path), "report", "--since", "1h", "--by", "tool", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    rows = {r["bucket"]: r for r in out["rows"]}
    assert rows["A"]["calls"] == 2
    assert rows["A"]["input_tokens"] == 30
