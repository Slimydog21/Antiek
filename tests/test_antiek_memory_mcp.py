"""Antiek Memory MCP server tests (Sprint 19, master-spec §13.8)."""

from __future__ import annotations

import io
import json

import pytest

from tools.antiek_memory import (
    AntiekMemoryServer,
    ResourceContent,
    ToolResult,
    compute_tool_hash,
    render_well_known_manifest,
    serve_stdio,
)
from tools.antiek_memory.server import CANONICAL_TOOLS, make_default_server


# ── Protocol compliance ──────────────────────────────────────────────


def test_initialize_returns_capabilities():
    server = make_default_server()
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
    })
    assert response is not None
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert "resources" in result["capabilities"]
    assert result["serverInfo"]["name"] == "antiek-memory"


def test_tools_list_returns_canonical_four():
    server = make_default_server()
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
    })
    assert response is not None
    tools = response["result"]["tools"]
    names = [t["name"] for t in tools]
    assert set(names) == {
        "search_personal", "search_public", "cite_source", "record_attribution",
    }


def test_tools_call_dispatches_to_handler():
    server = make_default_server()
    invoked = {}
    def handler(args: dict) -> ToolResult:
        invoked["args"] = args
        return ToolResult(content=[{
            "type": "text",
            "text": json.dumps({"chunks": [{"chunk_id": "c-1", "text": "test"}]}),
        }])

    server.handler_fns["search_personal"] = handler
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {
            "name": "search_personal",
            "arguments": {"query": "quantum", "top_k": 3},
        },
    })
    assert response is not None
    assert "result" in response
    assert response["result"]["isError"] is False
    assert invoked["args"] == {"query": "quantum", "top_k": 3}


def test_tools_call_unknown_returns_error():
    server = make_default_server()
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "nonexistent_tool", "arguments": {}},
    })
    assert response is not None
    assert response["error"]["code"] == -32601
    assert "nonexistent_tool" in response["error"]["message"]


def test_resources_list_returns_three_resources():
    server = make_default_server()
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {},
    })
    assert response is not None
    resources = response["result"]["resources"]
    assert len(resources) == 3
    uris = [r["uri"] for r in resources]
    assert any("private/notes" in u for u in uris)
    assert any("public/notes" in u for u in uris)
    assert any("books" in u for u in uris)


def test_resources_read_resolves_via_handler():
    server = make_default_server()
    def resolver(uri: str) -> ResourceContent:
        if uri.startswith("antiek://private/notes/"):
            return ResourceContent(
                uri=uri,
                mime_type="application/json",
                text=json.dumps({"note_text": "Test note"}),
            )
        return None  # type: ignore
    server.resource_handler = resolver
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 6, "method": "resources/read",
        "params": {"uri": "antiek://private/notes/user-1/note-1"},
    })
    assert response is not None
    contents = response["result"]["contents"]
    assert len(contents) == 1
    assert "note_text" in contents[0]["text"]


def test_unknown_method_returns_error():
    server = make_default_server()
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 7, "method": "unknown/thing", "params": {},
    })
    assert response is not None
    assert response["error"]["code"] == -32601


# ── Stdio transport ──────────────────────────────────────────────────


def test_stdio_processes_one_request_per_line():
    server = make_default_server()
    request_in = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
    })
    stdin = io.StringIO(request_in + "\n")
    stdout = io.StringIO()
    serve_stdio(server, stdin=stdin, stdout=stdout)
    output_lines = stdout.getvalue().strip().split("\n")
    assert len(output_lines) == 1
    response = json.loads(output_lines[0])
    assert response["id"] == 1
    assert "result" in response


def test_stdio_parse_error_returns_parse_error_response():
    server = make_default_server()
    stdin = io.StringIO("not valid json\n")
    stdout = io.StringIO()
    serve_stdio(server, stdin=stdin, stdout=stdout)
    response = json.loads(stdout.getvalue().strip())
    assert response["error"]["code"] == -32700
    assert response["id"] is None


# ── Signing / rug-pull defense ───────────────────────────────────────


def test_compute_tool_hash_is_deterministic():
    tool = CANONICAL_TOOLS[0]
    h1 = compute_tool_hash(tool)
    h2 = compute_tool_hash(tool)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex
    assert all(c in "0123456789abcdef" for c in h1)


def test_compute_tool_hash_changes_with_description():
    from dataclasses import replace
    t1 = CANONICAL_TOOLS[0]
    t2 = replace(t1, description=t1.description + " (rev 2)")
    assert compute_tool_hash(t1) != compute_tool_hash(t2)


def test_well_known_manifest_shape():
    manifest = render_well_known_manifest(list(CANONICAL_TOOLS))
    assert manifest["version"] == "1.0"
    assert manifest["server"] == "antiek-memory"
    assert len(manifest["tools"]) == 4
    for entry in manifest["tools"]:
        assert "name" in entry
        assert "description_sha256" in entry
        assert len(entry["description_sha256"]) == 64
