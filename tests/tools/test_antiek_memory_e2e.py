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
* tools/call record_attribution  → refuses unverified attribution

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


def _read_line(proc: subprocess.Popen, timeout: float = 20.0) -> dict:
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


def _run_once(db_path: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ANTIEK_DUCKDB_PATH"] = str(db_path)
    env["ANTIEK_MEMORY_OWNER"] = "testuser"
    env["ANTIEK_HOME"] = str(tmp_path / "home")
    return subprocess.run(
        [sys.executable, "-m", "tools.antiek_memory"],
        input=_rpc("initialize") + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd=str(Path(__file__).resolve().parents[2]),
        check=False,
    )


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
        con.execute(
            "INSERT INTO notebooks (notebook_id, title, owner_user_id, content_class) "
            "VALUES ('nb-own', 'Own notebook', 'testuser', 'user_owned')"
        )
        con.execute(
            "INSERT INTO notebook_blocks "
            "(block_id, notebook_id, block_index, block_type, content_json) "
            "VALUES ('block-own', 'nb-own', 0, 'note', ?)",
            [json.dumps({"text": "Own note content"})],
        )
        con.execute(
            "INSERT INTO notebooks (notebook_id, title, owner_user_id, content_class) "
            "VALUES ('nb-public', 'Released Notebook', 'other-user', 'user_public_contribution')"
        )
        con.execute(
            "INSERT INTO notebook_blocks "
            "(block_id, notebook_id, block_index, block_type, content_json) "
            "VALUES ('block-public', 'nb-public', 0, 'note', ?)",
            [json.dumps({"text": "Released note body"})],
        )
        con.execute(
            "INSERT INTO documents "
            "(document_id, title, author, source_tier, document_type, owner_user_id, content_class) "
            "VALUES ('doc-public', 'Public Paper', 'Public Author', 1, 'article', "
            "'__operator__', 'public_domain')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES ('chunk-public', 'doc-public', 0, 'Public quantum content')"
        )
        con.execute(
            "INSERT INTO documents "
            "(document_id, title, author, source_tier, document_type, owner_user_id, content_class) "
            "VALUES ('doc-unrelated', 'Unrelated Public Paper', 'Other Author', 1, 'article', "
            "'__operator__', 'public_domain')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES ('chunk-unrelated', 'doc-unrelated', 0, 'Garden content')"
        )
        con.execute(
            "INSERT INTO documents "
            "(document_id, title, author, source_tier, document_type, owner_user_id, content_class) "
            "VALUES ('doc-private-pd', 'Private Public Domain Library', 'Hidden Author', "
            "1, 'book', 'other-user', 'public_domain')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES ('chunk-private-pd', 'doc-private-pd', 0, 'Quantum private library body')"
        )
        con.execute(
            "INSERT INTO ip_holders (ip_holder_id, display_name, status) "
            "VALUES ('holder-1', 'Inactive Publisher', 'pre_onboarded')"
        )
        con.execute(
            "INSERT INTO documents "
            "(document_id, title, source_tier, document_type, owner_user_id, "
            "content_class, ip_holder_id) VALUES "
            "('doc-unlicensed', 'Unlicensed Edition', 1, 'book', '__operator__', "
            "'opt_in_licensed', 'holder-1')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES ('chunk-unlicensed', 'doc-unlicensed', 0, 'Quantum unlicensed body')"
        )
        con.execute(
            "INSERT INTO documents "
            "(document_id, title, source_tier, document_type, owner_user_id, content_class) "
            "VALUES ('doc-revoked', 'Revoked Edition', 1, 'book', '__operator__', 'public_domain')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES ('chunk-revoked', 'doc-revoked', 0, 'Quantum revoked body')"
        )
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES ('doc-revoked', TRUE)"
        )
        arxiv_cases = (
            (
                "doc-arxiv-nc", "chunk-arxiv-nc", "NC Paper", "Quasar NC body",
                {"source": "arxiv_oai_pmh", "arxiv_id": "2401.10001",
                 "license_uri": "http://creativecommons.org/licenses/by-nc/4.0/",
                 "rights_tier": "T1"},
            ),
            (
                "doc-arxiv-no-link", "chunk-arxiv-no-link", "No Link Paper",
                "Quasar missing link body",
                {"source": "arxiv_oai_pmh",
                 "license_uri": "http://creativecommons.org/licenses/by/4.0/",
                 "rights_tier": "T1"},
            ),
            (
                "doc-arxiv-t1", "chunk-arxiv-t1", "Allowed Paper", "Quasar allowed body",
                {"source": "arxiv_oai_pmh", "arxiv_id": "2401.10003",
                 "license_uri": "http://creativecommons.org/licenses/by/4.0/",
                 "rights_tier": "T1"},
            ),
        )
        for document_id, chunk_id, title, body, metadata in arxiv_cases:
            con.execute(
                "INSERT INTO documents "
                "(document_id, title, source_tier, document_type, owner_user_id, "
                "content_class, metadata) VALUES (?, ?, 1, 'article', '__operator__', "
                "'source_declared_open', ?)",
                [document_id, title, json.dumps(metadata)],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
                "VALUES (?, ?, 0, ?)",
                [chunk_id, document_id, body],
            )
    finally:
        con.close()
    return db_path


@pytest.fixture()
def server_proc(memory_db: Path, tmp_path: Path):
    """Spawn the Antiek Memory MCP server as a subprocess."""
    env = os.environ.copy()
    env["ANTIEK_DUCKDB_PATH"] = str(memory_db)
    # The owner this server process is launched for (the stdio transport's
    # only source of a verified identity).
    env["ANTIEK_MEMORY_OWNER"] = "testuser"
    # Also set ANTIEK_HOME to avoid touching the real home
    env["ANTIEK_HOME"] = str(tmp_path / "home")

    proc = subprocess.Popen(
        [sys.executable, "-m", "tools.antiek_memory"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(Path(__file__).resolve().parents[2]),
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

    def test_preinitialized_graph_starts_read_only(self, memory_db, tmp_path):
        before = memory_db.stat().st_mtime_ns
        completed = _run_once(memory_db, tmp_path)

        assert completed.returncode == 0
        assert json.loads(completed.stdout)["result"]["serverInfo"]["name"] == "antiek-memory"
        assert memory_db.stat().st_mtime_ns == before

    def test_absent_graph_exits_without_creating_file(self, tmp_path):
        missing = tmp_path / "missing" / "graph.duckdb"
        completed = _run_once(missing, tmp_path)

        assert completed.returncode != 0
        assert completed.stdout == ""
        assert "requires a readable, preinitialized graph" in completed.stderr
        assert not missing.parent.exists()

    def test_incomplete_graph_exits_without_schema_write(self, tmp_path):
        incomplete = tmp_path / "incomplete.duckdb"
        con = duckdb.connect(str(incomplete))
        try:
            con.execute("CREATE TABLE documents (document_id TEXT)")
        finally:
            con.close()

        completed = _run_once(incomplete, tmp_path)

        assert completed.returncode != 0
        assert completed.stdout == ""
        assert "requires a readable, preinitialized graph" in completed.stderr
        con = duckdb.connect(str(incomplete), read_only=True)
        try:
            tables = con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
        finally:
            con.close()
        assert tables == [("documents",)]

    def test_unreadable_graph_exits_without_replacing_file(self, tmp_path):
        invalid = tmp_path / "corrupt.duckdb"
        original = b"not a DuckDB database"
        invalid.write_bytes(original)

        completed = _run_once(invalid, tmp_path)

        assert completed.returncode != 0
        assert completed.stdout == ""
        assert "requires a readable, preinitialized graph" in completed.stderr
        assert invalid.read_bytes() == original


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
            {"uri": "antiek://private/notes/testuser/block-own"},
            rpc_id=4,
        )
        assert "result" in resp
        contents = resp["result"]["contents"]
        assert len(contents) == 1
        content = contents[0]
        assert content["uri"] == "antiek://private/notes/testuser/block-own"
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
            {"uri": "antiek://private/notes/testuser/block-own"},
            rpc_id=4,
        )
        body = json.loads(resp["result"]["contents"][0]["text"])
        assert body["user_id"] == "testuser"
        assert body["title"] == "Own notebook"

    @pytest.mark.parametrize("uri", [
        "antiek://private/notes/__operator__/block-1",
        "antiek://private/notes/testuser/block-1",
        "antiek://private/notes/testuser/block-own/extra",
        "antiek://private/notes/testuser/%62lock-own",
        "antiek://private/notes/testuser/block-own?owner=__operator__",
        "antiek://private/notes/testuser/../block-1",
        "antiek://books/arbitrary-isbn/chunk-1",
        "antiek://books/arbitrary-isbn/chunk-public",
        "antiek://books/arbitrary-isbn/chunk-private-pd",
        "antiek://books/arbitrary-isbn/chunk-revoked",
    ])
    def test_wrong_owner_and_hostile_uris_return_no_private_data(self, server_proc, uri):
        resp = _send_and_recv(server_proc, "resources/read", {"uri": uri}, rpc_id=4)
        assert resp["error"]["code"] == -32602
        wire = json.dumps(resp)
        for secret in (
            "Private note content", "Test Notebook", "Test Paper", "Alice",
            "Public Paper", "Private Public Domain Library", "Revoked Edition",
        ):
            assert secret not in wire

    def test_private_note_client_claim_for_another_owner_is_refused(self, server_proc):
        resp = _send_and_recv(
            server_proc, "resources/read",
            {"uri": "antiek://private/notes/testuser/block-own",
             "auth_context": {"user_id": "__operator__"}}, rpc_id=4,
        )
        assert resp["error"]["code"] == -32602
        assert "Own note content" not in json.dumps(resp)

    def test_public_note_requires_current_public_class_and_note_type(self, server_proc):
        allowed = _send_and_recv(
            server_proc, "resources/read", {"uri": "antiek://public/notes/block-public"}, rpc_id=4,
        )
        assert "Released note body" in allowed["result"]["contents"][0]["text"]
        for uri in (
            "antiek://public/notes/block-1",
            "antiek://public/notes/block-own",
            "antiek://public/notes/block-public/extra",
        ):
            denied = _send_and_recv(server_proc, "resources/read", {"uri": uri}, rpc_id=5)
            assert denied["error"]["code"] == -32602
            assert "Private note content" not in json.dumps(denied)
            assert "Own note content" not in json.dumps(denied)

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
    """tools/call search_personal — owner-scoped, fail-closed over the wire.

    The ranked path itself (query changes the answer, owners are disjoint) is
    pinned in ``test_antiek_memory_search_personal.py`` with an injected
    embedding stub; a subprocess cannot take one, so these two cases cover what
    only the wire can prove: the transport-level ``auth_context`` reaches the
    handler, and its absence yields an error rather than the sentinel owner's
    chunks that this tool used to return to everyone.
    """

    def test_search_personal_claiming_another_owner_fails_closed(self, server_proc):
        # The process is launched for ``testuser``; a client naming anyone
        # else over stdio is refused rather than answered as that owner.
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "search_personal",
                "arguments": {"query": "test", "top_k": 10},
                "auth_context": {"user_id": "someone-else"},
            },
            rpc_id=5,
        )
        assert "result" in resp
        assert resp["result"]["isError"] is True
        body = json.loads(resp["result"]["content"][0]["text"])
        assert body["chunks"] == []
        assert "auth_context" in body["error"]

    def test_search_personal_scopes_to_the_authenticated_owner(self, server_proc):
        # The fixture's document belongs to the storage sentinel, which no
        # per-user scope can name; a distinct owner who owns nothing gets an
        # honest empty answer, not that document's chunks.
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "search_personal",
                "arguments": {"query": "test", "top_k": 10},
                "auth_context": {"user_id": "testuser"},
            },
            rpc_id=5,
        )
        assert resp["result"]["isError"] is False
        body = json.loads(resp["result"]["content"][0]["text"])
        assert body["chunks"] == []
        assert body["query"] == "test"


class TestToolsCallSearchPublic:
    """tools/call search_public returns only matching, proven public rows."""

    def test_search_public_wraps_in_envelope(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "search_public",
                "arguments": {"query": "quantum", "top_k": 10},
            },
            rpc_id=5,
        )
        assert resp["result"]["isError"] is False
        body = json.loads(resp["result"]["content"][0]["text"])
        assert [chunk["chunk_id"] for chunk in body["chunks"]] == ["chunk-public"]
        # §13.8: public results must be wrapped in prompt-injection envelope
        for chunk in body["chunks"]:
            assert '<antiek:content trusted="false">' in chunk["text"]

    def test_search_public_nonmatching_query_and_private_body_do_not_leak(self, server_proc):
        resp = _send_and_recv(server_proc, "tools/call", {
            "name": "search_public", "arguments": {"query": "first chunk", "top_k": 10},
        }, rpc_id=5)
        body = json.loads(resp["result"]["content"][0]["text"])
        assert body["chunks"] == []
        assert "Test Paper" not in json.dumps(resp)
        assert "Alice" not in json.dumps(resp)

    def test_search_public_excludes_private_rights_and_revoked_rows(self, server_proc):
        resp = _send_and_recv(server_proc, "tools/call", {
            "name": "search_public", "arguments": {"query": "quantum", "top_k": 50},
        }, rpc_id=5)
        body = json.loads(resp["result"]["content"][0]["text"])
        assert [chunk["chunk_id"] for chunk in body["chunks"]] == ["chunk-public"]
        wire = json.dumps(resp)
        for secret in ("Private Public Domain Library", "Hidden Author", "Unlicensed Edition", "Revoked Edition"):
            assert secret not in wire

    def test_search_public_rechecks_immutable_arxiv_rights(self, server_proc):
        resp = _send_and_recv(server_proc, "tools/call", {
            "name": "search_public", "arguments": {"query": "quasar", "top_k": 50},
        }, rpc_id=5)
        assert resp["result"]["isError"] is False
        body = json.loads(resp["result"]["content"][0]["text"])
        assert [chunk["chunk_id"] for chunk in body["chunks"]] == ["chunk-arxiv-t1"]
        wire = json.dumps(resp)
        for secret in ("Quasar NC body", "NC Paper", "Quasar missing link body", "No Link Paper"):
            assert secret not in wire


class TestToolsCallCiteSource:
    """tools/call cite_source — resolves chunk metadata."""

    def test_cite_source_returns_document_metadata(self, server_proc):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "cite_source",
                "arguments": {"id": "chunk-public", "id_type": "chunk"},
            },
            rpc_id=5,
        )
        assert resp["result"]["isError"] is False
        citation = json.loads(resp["result"]["content"][0]["text"])
        assert citation["chunk_id"] == "chunk-public"
        assert citation["document_id"] == "doc-public"
        assert citation["title"] == "Public Paper"
        assert citation["source_tier"] == 1
        assert citation["author"] == "Public Author"

    def test_cite_source_refuses_foreign_private_metadata(self, server_proc):
        resp = _send_and_recv(server_proc, "tools/call", {
            "name": "cite_source", "arguments": {"id": "chunk-1", "id_type": "chunk"},
        }, rpc_id=5)
        assert resp["result"]["isError"] is True
        wire = json.dumps(resp)
        for secret in ("Test Paper", "Alice", "doc-1", "first chunk"):
            assert secret not in wire

    @pytest.mark.parametrize("chunk_id", [
        "chunk-private-pd", "chunk-unlicensed", "chunk-revoked",
    ])
    def test_cite_source_refuses_unpublished_or_revoked_metadata(self, server_proc, chunk_id):
        resp = _send_and_recv(server_proc, "tools/call", {
            "name": "cite_source", "arguments": {"id": chunk_id, "id_type": "chunk"},
        }, rpc_id=5)
        assert resp["result"]["isError"] is True
        wire = json.dumps(resp)
        for secret in ("Private Public Domain Library", "Hidden Author", "Unlicensed Edition", "Revoked Edition"):
            assert secret not in wire

    def test_cite_source_preserves_own_private_metadata(self, server_proc, memory_db):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        con = duckdb.connect(str(memory_db), read_only=False)
        try:
            con.execute(
                "INSERT INTO documents "
                "(document_id, title, author, source_tier, document_type, owner_user_id, content_class) "
                "VALUES ('doc-own', 'Own Document', 'Own Author', 1, 'article', 'testuser', 'user_owned')"
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
                "VALUES ('chunk-own', 'doc-own', 0, 'Private own body')"
            )
        finally:
            con.close()
        resp = _send_and_recv(server_proc, "tools/call", {
            "name": "cite_source", "arguments": {"id": "chunk-own", "id_type": "chunk"},
        }, rpc_id=5)
        assert resp["result"]["isError"] is False
        citation = json.loads(resp["result"]["content"][0]["text"])
        assert citation["title"] == "Own Document"

    def test_cite_source_returns_public_bibliography_without_body(self, server_proc):
        resp = _send_and_recv(server_proc, "tools/call", {
            "name": "cite_source", "arguments": {"id": "chunk-arxiv-nc", "id_type": "chunk"},
        }, rpc_id=5)
        assert resp["result"]["isError"] is False
        citation = json.loads(resp["result"]["content"][0]["text"])
        assert citation["title"] == "NC Paper"
        assert "Quasar NC body" not in json.dumps(resp)

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
    """Unverified client attribution never enters the payout audit."""

    @pytest.mark.parametrize("chunk_id", ["chunk-1", "chunk-public"])
    def test_record_attribution_refuses_unverified_event(self, server_proc, memory_db, chunk_id):
        _send_and_recv(server_proc, "initialize", {}, rpc_id=1)
        resp = _send_and_recv(
            server_proc,
            "tools/call",
            {
                "name": "record_attribution",
                "arguments": {
                    "chunk_id": chunk_id,
                    "investigation_id": "inv-1",
                    "session_dwell_seconds": 42.5,
                },
            },
            rpc_id=5,
        )
        assert resp["result"]["isError"] is True
        assert chunk_id not in json.dumps(resp)

        # Verify the attribution was actually recorded in the DB
        import duckdb as _duckdb
        con = _duckdb.connect(str(memory_db), read_only=True)
        try:
            row = con.execute(
                "SELECT * FROM attribution_audit WHERE page_id = ?",
                [chunk_id],
            ).fetchone()
            assert row is None
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
