"""Antiek Memory MCP server — end-to-end subprocess harness.

Spawns the server as a subprocess (``python -m tools.antiek_memory``),
drives the JSON-RPC wire protocol over stdin/stdout, and asserts the
full protocol surface per master-spec §13.8:

* initialize handshake
* tools/list  → 4 canonical tools + schemas
* resources/list  → 3 resource templates
* resources/read  → prompt-injection envelope (§13.8.3)
* tools/call search_personal  → real substrate query path
* tools/call cite_source  → resolves chunk metadata
* tools/call record_attribution  → records attribution event

No new deps; uses subprocess + json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from substrate.graph.schema import init_database_at_path

# ── helpers ──────────────────────────────────────────────────────────


def _rpc(method: str, params: dict | None = None, rpc_id: int = 1) -> str:
    """Serialize a JSON-RPC 2.0 request (one line)."""
    return json.dumps({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": method,
        "params": params or {},
    })


def _read_line(proc: subprocess.Popen, timeout: float = 10.0) -> dict:
    """Read one JSON line from the server's stdout with a timeout."""
    import select
    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        raise TimeoutError(f"Server did not respond within {timeout}s")
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("Server stdout closed unexpectedly")
    return json.loads(line.decode())


def _send_and_recv(
    proc: subprocess.Popen,
    method: str,
    params: dict | None = None,
    rpc_id: int = 1,
) -> dict:
    """Send one request and read one response."""
    proc.stdin.write((_rpc(method, params, rpc_id) + "\n").encode())
    proc.stdin.flush()
    return _read_line(proc)


# ── fixture setup ────────────────────────────────────────────────────


@pytest.fixture()
def memory_db(tmp_path: Path) -> Path:
    """Create a temp DuckDB with schema + fixtures for the MCP server.

    Inserts:
    - One document (doc-1)
    - Two chunks (chunk-1, chunk-2)
    - One notebook (nb-1, owner='testuser')
    - One notebook_block (block-1, type='note')
    """
    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    con = duckdb.connect(str(db_path), read_only=False)
    try:
        con.execute(
            """
            INSERT INTO documents
                (document_id, source_uri, title, author, source_tier,
                 document_type, owner_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "doc-1", "https://example.com/paper",
                "Test Paper", "Alice", 1, "article", "__operator__",
            ],
        )
        con.execute(
            """
            INSERT INTO chunks
                (chunk_id, document_id, chunk_index, text, token_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            ["chunk-1", "doc-1", 0, "The first chunk of the test document.", 8],
        )
        con.execute(
            """
            INSERT INTO chunks
                (chunk_id, document_id, chunk_index, text, token_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            ["chunk-2", "doc-1", 1, "The second chunk with more content.", 7],
        )
        con.execute(
            """
            INSERT INTO notebooks
                (notebook_id, title, owner_user_id, content_class)
            VALUES (?, ?, ?, ?)
            """,
            ["nb-1", "Test Notebook", "__operator__", "user_owned"],
        )
        con.execute(
            """
            INSERT INTO notebook_blocks
                (block_id, notebook_id, block_index, block_type, ref_id, content_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                "block-1", "nb-1", 0, "note", "note-1",
                json.dumps({"text": "Private note content for testing."}),
            ],
        )
    finally:
        con.close()
    return db_path


@pytest.fixture()
def server_proc(memory_db: Path, tmp_path: Path):
    """Spawn the Antiek Memory MCP server as a subprocess."""
    env = os.environ.copy()
    env["ANTIEK_DUCKDB_PATH"] = str(memory_db)
    # Also set ANTIEK_HOME to avoid touching the real home
    env["ANTIEK_HOME"] = str(tmp_path / "home")

    proc = subprocess.Popen(
        [sys.executable, "-m", "tools.antiek_memory"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd="/tmp/antiek-wt-memory-mcp",
    )
    yield proc
    proc.stdin.close()
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ── tests ────────────────────────────────────────────────────────────


class TestInitializeHandshake:
    """§13.8: server must respond to 'initialize' with capabilities."""

    def test_initialize_returns_protocol_version_and_capabilities(self, server_proc):
        resp = _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]
        assert "resources" in result["capabilities"]
        assert result["serverInfo"]["name"] == "antiek-memory"


class TestToolsList:
    """§13.8: server must expose exactly four canonical tools."""

    def test_tools_list_returns_four_tools(self, server_proc):
        # First initialize (some servers require it)
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "tools/list", {}, rpc_id=2)
        assert "result" in resp
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert names == {
            "search_personal",
            "search_public",
            "cite_source",
            "record_attribution",
        }

    def test_each_tool_has_name_description_and_input_schema(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "tools/list", {}, rpc_id=2)
        for tool in resp["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            schema = tool["inputSchema"]
            assert schema["type"] == "object"
            assert "properties" in schema

    def test_search_personal_requires_query(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "tools/list", {}, rpc_id=2)
        tools = {t["name"]: t for t in resp["result"]["tools"]}
        schema = tools["search_personal"]["inputSchema"]
        assert "query" in schema["required"]

    def test_search_public_requires_query(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "tools/list", {}, rpc_id=2)
        tools = {t["name"]: t for t in resp["result"]["tools"]}
        schema = tools["search_public"]["inputSchema"]
        assert "query" in schema["required"]

    def test_cite_source_requires_id(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "tools/list", {}, rpc_id=2)
        tools = {t["name"]: t for t in resp["result"]["tools"]}
        schema = tools["cite_source"]["inputSchema"]
        assert "id" in schema["required"]

    def test_record_attribution_requires_chunk_id_and_investigation_id(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "tools/list", {}, rpc_id=2)
        tools = {t["name"]: t for t in resp["result"]["tools"]}
        schema = tools["record_attribution"]["inputSchema"]
        assert "chunk_id" in schema["required"]
        assert "investigation_id" in schema["required"]


class TestResourcesList:
    """§13.8: server must expose exactly three resource templates."""

    def test_resources_list_returns_three_templates(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "resources/list", {}, rpc_id=3)
        assert "result" in resp
        resources = resp["result"]["resources"]
        assert len(resources) == 3

    def test_resource_uris_match_spec(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "resources/list", {}, rpc_id=3)
        uris = {r["uri"] for r in resp["result"]["resources"]}
        assert "antiek://private/notes/{user_id}/{note_id}" in uris
        assert "antiek://public/notes/{note_id}" in uris
        assert "antiek://books/{isbn}/{chunk_id}" in uris

    def test_each_resource_has_mime_type(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "resources/list", {}, rpc_id=3)
        for r in resp["result"]["resources"]:
            assert r["mimeType"] == "application/json"


class TestResourcesRead:
    """§13.8.3: private notes must be wrapped in prompt-injection envelope."""

    def test_private_note_returns_content_with_envelope(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "resources/read",
            {"uri": "antiek://private/notes/__operator__/block-1"},
            rpc_id=4,
        )
        assert "result" in resp
        contents = resp["result"]["contents"]
        assert len(contents) == 1
        content = contents[0]
        assert content["uri"] == "antiek://private/notes/__operator__/block-1"
        assert content["mimeType"] == "application/json"

        # Parse the JSON text to check the envelope
        body = json.loads(content["text"])
        assert "content" in body
        # §13.8.3: content must be wrapped in <antiek:content trusted="false">
        assert '<antiek:content trusted="false">' in body["content"]
        assert "</antiek:content>" in body["content"]

    def test_private_note_includes_user_id_and_title(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "resources/read",
            {"uri": "antiek://private/notes/__operator__/block-1"},
            rpc_id=4,
        )
        body = json.loads(resp["result"]["contents"][0]["text"])
        assert body["user_id"] == "__operator__"
        assert body["title"] == "Test Notebook"

    def test_private_note_nonexistent_returns_error(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "resources/read",
            {"uri": "antiek://private/notes/testuser/nonexistent"},
            rpc_id=4,
        )
        assert "error" in resp

    def test_unknown_uri_scheme_returns_error(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "resources/read",
            {"uri": "antiek://unknown/resource"},
            rpc_id=4,
        )
        assert "error" in resp


class TestToolsCallSearchPersonal:
    """tools/call search_personal — real substrate query path."""

    def test_search_personal_returns_chunks_from_substrate(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "search_personal",
                "arguments": {"query": "test", "top_k": 10},
            },
            rpc_id=5,
        )
        assert "result" in resp
        assert resp["result"]["isError"] is False
        content = resp["result"]["content"]
        assert len(content) >= 1
        body = json.loads(content[0]["text"])
        assert "chunks" in body
        assert len(body["chunks"]) == 2  # both chunks from doc-1
        chunk_ids = {c["chunk_id"] for c in body["chunks"]}
        assert chunk_ids == {"chunk-1", "chunk-2"}

    def test_search_personal_respects_top_k(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "search_personal",
                "arguments": {"query": "test", "top_k": 1},
            },
            rpc_id=5,
        )
        body = json.loads(resp["result"]["content"][0]["text"])
        assert len(body["chunks"]) == 1


class TestToolsCallSearchPublic:
    """tools/call search_public — wraps results in prompt-injection envelope."""

    def test_search_public_wraps_in_envelope(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "search_public",
                "arguments": {"query": "test", "top_k": 10},
            },
            rpc_id=5,
        )
        assert resp["result"]["isError"] is False
        body = json.loads(resp["result"]["content"][0]["text"])
        assert len(body["chunks"]) >= 1
        # §13.8: public results must be wrapped in prompt-injection envelope
        for chunk in body["chunks"]:
            assert '<antiek:content trusted="false">' in chunk["text"]


class TestToolsCallCiteSource:
    """tools/call cite_source — resolves chunk metadata."""

    def test_cite_source_returns_document_metadata(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "cite_source",
                "arguments": {"id": "chunk-1", "id_type": "chunk"},
            },
            rpc_id=5,
        )
        assert resp["result"]["isError"] is False
        citation = json.loads(resp["result"]["content"][0]["text"])
        assert citation["chunk_id"] == "chunk-1"
        assert citation["document_id"] == "doc-1"
        assert citation["title"] == "Test Paper"
        assert citation["source_tier"] == 1
        assert citation["author"] == "Alice"

    def test_cite_source_nonexistent_returns_error(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "cite_source",
                "arguments": {"id": "nonexistent", "id_type": "chunk"},
            },
            rpc_id=5,
        )
        assert resp["result"]["isError"] is True


class TestToolsCallRecordAttribution:
    """tools/call record_attribution — records attribution event without escrow."""

    def test_record_attribution_records_event(self, server_proc, memory_db):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "record_attribution",
                "arguments": {
                    "chunk_id": "chunk-1",
                    "investigation_id": "inv-1",
                    "session_dwell_seconds": 42.5,
                },
            },
            rpc_id=5,
        )
        assert resp["result"]["isError"] is False
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["status"] == "recorded"
        assert result["chunk_id"] == "chunk-1"
        assert result["investigation_id"] == "inv-1"
        assert "audit_id" in result

        # Verify the attribution was actually recorded in the DB
        import duckdb as _duckdb
        con = _duckdb.connect(str(memory_db), read_only=True)
        try:
            row = con.execute(
                "SELECT * FROM attribution_audit WHERE page_id = ?",
                ["chunk-1"],
            ).fetchone()
            assert row is not None, "attribution_audit row not found"
        finally:
            con.close()


class TestErrorHandling:
    """Edge cases and error paths."""

    def test_unknown_method_returns_error(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(server_proc, "unknown/method", {}, rpc_id=99)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_unknown_tool_returns_error(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {"name": "nonexistent_tool", "arguments": {}},
            rpc_id=5,
        )
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_parse_error_returns_parse_error(self, server_proc):
        server_proc.stdin.write(b"not valid json\n")
        server_proc.stdin.flush()
        resp = _read_line(server_proc)
        assert resp["error"]["code"] == -32700
