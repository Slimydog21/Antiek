"""Rug-pull defense for the Antiek MCP server.

Invariant Labs April 2025 disclosure mitigation: tool description
hashes are published in a static ``.well-known/mcp-tools.json``
manifest. Clients fetch this from the server's known origin and verify
each tool's SHA-256 hash matches the live ``tools/list`` response.
Drift between the manifest and the live description is treated as a
fatal session-termination event — the tool may have been replaced
with a malicious variant.

Hash inputs: tool name + description string, canonical JSON with
``sort_keys=True`` and compact separators.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def compute_tool_hash(name: str, description: str) -> str:
    """Compute a deterministic SHA-256 hash of a tool's identity.

    Hash inputs are the tool *name* and *description*, serialized as
    canonical JSON (sorted keys, no whitespace). The hash is
    reproducible across runs and independent of registration order.
    """
    canonical = json.dumps(
        {"name": name, "description": description},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_tool_hash(
    name: str,
    description: str,
    expected_hash: str,
) -> bool:
    """Return True if the live tool description matches the expected hash.

    Used by clients on every session refresh. A mismatch means the
    tool description drifted from the manifest — potential rug-pull.
    """
    return compute_tool_hash(name, description) == expected_hash


def generate_manifest(tools: list[dict[str, str]]) -> dict[str, Any]:
    """Generate a ``.well-known/mcp-tools.json`` manifest.

    Each entry in *tools* must have ``name`` and ``description`` keys.
    The manifest is a static JSON document that clients compare against
    the live ``tools/list`` response.

    Returns:
        Manifest dict with version, server name, and per-tool hashes.
    """
    return {
        "version": "1.0",
        "server": "antiek",
        "tools": [
            {
                "name": t["name"],
                "description_sha256": compute_tool_hash(t["name"], t["description"]),
            }
            for t in tools
        ],
    }


def write_manifest(
    tools: list[dict[str, str]],
    path: Path | str,
) -> Path:
    """Write the manifest to *path* and return the resolved Path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(generate_manifest(tools), indent=2) + "\n")
    return p


def load_manifest(path: Path | str) -> dict[str, Any]:
    """Load a manifest from *path*."""
    data: dict[str, Any] = json.loads(Path(path).read_text())
    return data


def verify_manifest(
    tools: list[dict[str, str]],
    manifest: dict[str, Any],
) -> list[str]:
    """Verify live tools against a manifest.

    Returns a list of tool names whose manifest entries drifted from the
    live server. An empty list means the static manifest and live
    ``tools/list`` response contain the same tool names with the same
    descriptions — safe to proceed.
    """
    manifest_hashes: dict[str, str] = {
        entry["name"]: entry["description_sha256"]
        for entry in manifest.get("tools", [])
    }
    live_names = {t["name"] for t in tools}
    drifted: list[str] = []
    for t in tools:
        expected = manifest_hashes.get(t["name"])
        if expected is None or not verify_tool_hash(t["name"], t["description"], expected):
            drifted.append(t["name"])
    for name in manifest_hashes:
        if name not in live_names:
            drifted.append(name)
    return drifted
