"""Tool-description signing for Antiek Memory MCP (master-spec §13.8).

Rug-pull defense per Invariant Labs April 2025: tool description
hashes are published in `.well-known/mcp-tools.json`; clients verify
on every refresh. Drift treated as fatal session-termination event.

The signing is deterministic (SHA-256 over canonical JSON) so a
client can re-compute the expected hash and refuse a session if the
tool description has changed without a corresponding manifest update.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .server import ToolDescription


def compute_tool_hash(tool: ToolDescription) -> str:
    """Compute the SHA-256 hash of a tool description, deterministic
    across runs. Hash inputs: name, description, input_schema (the
    full schema dict serialized with sort_keys=True)."""
    canonical = json.dumps({
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_well_known_manifest(tools: list[ToolDescription]) -> dict[str, Any]:
    """Render the `.well-known/mcp-tools.json` manifest. Clients fetch
    this from the server's known origin and verify each tool's hash
    matches the hash in tools/list responses. Drift = rug-pull;
    sessions terminate.

    Per §13.8: 'Tool description hashes published in
    .well-known/mcp-tools.json manifest; clients verify on every
    refresh. Drift treated as fatal session-termination event.'
    """
    return {
        "version": "1.0",
        "server": "antiek-memory",
        "tools": [
            {
                "name": t.name,
                "description_sha256": compute_tool_hash(t),
            }
            for t in tools
        ],
    }
