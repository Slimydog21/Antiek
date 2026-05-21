"""Antiek Memory MCP server (master-spec §13.8, Sprint 19-20).

Exposes the user's personal graph (§13.2 — the user's memory) to
external LLMs through the Model Context Protocol. Per master-spec
§13.8: MCP is the only defensible primary developer surface as of
mid-2026 (~97M monthly SDK downloads, ~2K registered servers, 92%
adoption among 2025-2026 agent frameworks per BCG).

Three URI-addressable resources:
- antiek://private/notes/{user_id}/{note_id}
- antiek://public/notes/{note_id}
- antiek://books/{isbn}/{chunk_id}

Four tools:
- search_personal
- search_public
- cite_source
- record_attribution

Security architecture per §13.8 + Invariant Labs April 2025 disclosures:
- Signed tool descriptions in .well-known/mcp-tools.json
- Prompt-injection envelopes (<antiek:content trusted="false">...</antiek:content>)
- Rug-pull defense via tool description hashes
- Per-user OAuth scope on the private resource

This module ships the protocol-compliant server scaffold without
depending on the `mcp` Python SDK (which is not in Antiek's deps
yet). The wire protocol is JSON-RPC 2.0 over stdio. Operator can
swap in the SDK at integration time.
"""

from .server import (
    AntiekMemoryServer,
    ResourceContent,
    ToolDescription,
    ToolResult,
    serve_stdio,
)
from .signing import compute_tool_hash, render_well_known_manifest

__all__ = [
    "AntiekMemoryServer",
    "ResourceContent",
    "ToolDescription",
    "ToolResult",
    "compute_tool_hash",
    "render_well_known_manifest",
    "serve_stdio",
]
