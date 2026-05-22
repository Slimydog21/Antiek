"""GET /.well-known/mcp-tools.json — rug-pull defense manifest (§13.8)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_AUTH_SECRET", raising=False)
    from interfaces.research.api.app import create_app
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def test_manifest_endpoint_returns_200(client: TestClient):
    r = client.get("/.well-known/mcp-tools.json")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "1.0"
    assert body["server"] == "antiek-memory"


def test_manifest_lists_all_canonical_tools(client: TestClient):
    from tools.antiek_memory.server import CANONICAL_TOOLS

    r = client.get("/.well-known/mcp-tools.json")
    body = r.json()
    tool_names = {t["name"] for t in body["tools"]}
    canonical_names = {t.name for t in CANONICAL_TOOLS}
    assert tool_names == canonical_names


def test_manifest_hashes_match_signing_module(client: TestClient):
    """The endpoint must agree byte-for-byte with the signing module
    so a client that computes hashes locally gets the same result."""
    from tools.antiek_memory.server import CANONICAL_TOOLS
    from tools.antiek_memory.signing import compute_tool_hash

    r = client.get("/.well-known/mcp-tools.json")
    body = r.json()

    expected = {t.name: compute_tool_hash(t) for t in CANONICAL_TOOLS}
    for entry in body["tools"]:
        assert entry["description_sha256"] == expected[entry["name"]]


def test_manifest_is_publicly_reachable_without_auth(monkeypatch):
    """The manifest path is in _OPERATOR_AUTH_OPEN_PATHS so MCP
    clients can fetch it without an Antiek session."""
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "operator@test.example")
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "machine-tok")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "x" * 48)
    from interfaces.research.api.app import create_app
    c = TestClient(create_app(register_wrestling=False, register_providers=False))

    r = c.get("/.well-known/mcp-tools.json")  # no auth headers
    assert r.status_code == 200
