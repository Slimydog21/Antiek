"""MCP attribution records must be authenticated, eligible, and replayable."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.ad_inventory import attribution_audit
from substrate.ad_inventory.attribution import ATTRIBUTION_ALGORITHM_VERSION
from substrate.graph.schema import init_database_at_path
from tools.antiek_memory.__main__ import _make_handlers
from tools.antiek_memory.server import AntiekMemoryServer, ToolResult


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(path)
    with connect_write(path, purpose="seed-mcp-attribution") as con:
        for document_id, content_class, owner, chunk_id in (
            ("doc-pd", "public_domain", "__operator__", "chunk-pd"),
            ("doc-priv", "user_owned", "user-b", "chunk-priv"),
            ("doc-pr", "personal_reading", "__operator__", "chunk-pr"),
            ("doc-r", "restricted_pending_opt_in", "__operator__", "chunk-r"),
        ):
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, owner_user_id, content_class) "
                "VALUES (?, ?, 1, 'article', ?, ?)",
                [document_id, document_id, owner, content_class],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
                "VALUES (?, ?, 0, 'test chunk')",
                [chunk_id, document_id],
            )
    return path


def _call(
    db_path: str,
    *,
    chunk_id: Any = "chunk-pd",
    investigation_id: Any = "inv-1",
    auth_context: object = {"user_id": "owner-a"},
    **extra: Any,
) -> ToolResult:
    handlers, _resources = _make_handlers(db_path)
    return handlers["record_attribution"](
        {"chunk_id": chunk_id, "investigation_id": investigation_id, **extra},
        auth_context=auth_context,
    )


def _body(result: ToolResult) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(result.content[0]["text"])
    return body


def _row_count(db_path: str) -> int:
    con = connect_read(db_path)
    try:
        row = con.execute("SELECT count(*) FROM attribution_audit").fetchone()
        assert row is not None
        return int(row[0])
    finally:
        con.close()


def test_unknown_chunk_is_rejected_and_writes_nothing(db_path: str) -> None:
    result = _call(db_path, chunk_id="chunk-DOES-NOT-EXIST")
    assert result.is_error is True
    assert _body(result)["error"] == "chunk_id is not a public-graph chunk"
    assert _row_count(db_path) == 0


def test_private_and_personal_chunks_are_rejected_with_the_same_message(db_path: str) -> None:
    unknown = _body(_call(db_path, chunk_id="chunk-DOES-NOT-EXIST"))["error"]
    for chunk_id in ("chunk-priv", "chunk-pr"):
        result = _call(db_path, chunk_id=chunk_id)
        assert result.is_error is True
        assert _body(result)["error"] == unknown
    assert _row_count(db_path) == 0


@pytest.mark.parametrize("auth_context", [None, {}, {"user_id": "__operator__"}])
def test_unauthenticated_call_is_rejected(db_path: str, auth_context: object) -> None:
    result = _call(db_path, auth_context=auth_context)
    assert result.is_error is True
    assert _body(result) == {
        "status": "rejected",
        "error": "record_attribution requires an authenticated per-user owner "
        "in auth_context.user_id",
    }
    assert _row_count(db_path) == 0


def test_recorded_row_replays_identically(db_path: str) -> None:
    result = _call(db_path, session_dwell_seconds=42.5)
    assert result.is_error is False
    body = _body(result)
    assert body == {
        "status": "recorded",
        "audit_id": body["audit_id"],
        "chunk_id": "chunk-pd",
        "document_id": "doc-pd",
        "investigation_id": "inv-1",
        "impression_set_ref": "mcp:owner-a:inv-1",
        "algorithm": "equal_split_per_chunk_citation",
        "algorithm_version": ATTRIBUTION_ALGORITHM_VERSION,
        "dwell_seconds": 42.5,
    }
    with connect_write(db_path, purpose="verify-mcp-attribution") as con:
        assert attribution_audit.replay(con, body["audit_id"]).identical is True
        record = attribution_audit.load_record(con, body["audit_id"])
    assert record is not None
    assert record.algorithm_version == ATTRIBUTION_ALGORITHM_VERSION
    assert record.inputs == {"chunk_to_document": {"chunk-pd": "doc-pd"}}
    assert record.shares == {"doc-pd": 1.0}
    assert record.impression_set_ref == "mcp:owner-a:inv-1"


def test_retry_is_idempotent(db_path: str) -> None:
    first = _call(db_path, session_dwell_seconds=1)
    second = _call(db_path, session_dwell_seconds=10)
    assert first.is_error is False
    assert second.is_error is False
    assert _body(first)["audit_id"] == _body(second)["audit_id"]
    assert _row_count(db_path) == 1


def test_restricted_chunk_is_recorded(db_path: str) -> None:
    result = _call(db_path, chunk_id="chunk-r")
    assert result.is_error is False
    with connect_write(db_path, purpose="verify-restricted-attribution") as con:
        assert attribution_audit.replay(con, _body(result)["audit_id"]).identical is True


@pytest.mark.parametrize(
    "override",
    [
        {"session_dwell_seconds": -1},
        {"session_dwell_seconds": True},
        {"session_dwell_seconds": "5"},
        {"session_dwell_seconds": float("nan")},
        {"chunk_id": ""},
        {"investigation_id": 7},
    ],
)
def test_invalid_arguments_are_rejected(db_path: str, override: dict[str, Any]) -> None:
    result = _call(db_path, **override)
    assert result.is_error is True
    assert _body(result)["status"] == "rejected"
    assert _row_count(db_path) == 0


def test_server_passes_bound_owner(db_path: str) -> None:
    handlers, _resources = _make_handlers(db_path)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "record_attribution",
            "arguments": {"chunk_id": "chunk-pd", "investigation_id": "inv-1"},
        },
    }
    bound = AntiekMemoryServer(handler_fns=handlers, bound_owner="owner-a")
    response = bound.handle_request(request)
    assert response is not None
    assert response["result"]["isError"] is False
    assert json.loads(response["result"]["content"][0]["text"])[
        "impression_set_ref"
    ] == "mcp:owner-a:inv-1"

    unbound = AntiekMemoryServer(handler_fns=handlers)
    response = unbound.handle_request(request)
    assert response is not None
    assert response["result"]["isError"] is True
    assert _row_count(db_path) == 1
