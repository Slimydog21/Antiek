"""Pin Antiek Memory MCP tool hashes in a reviewed, committed manifest.

The HTTP endpoint serves the file verbatim. CI fails when live descriptions
drift, and the stdio server refuses to start on drift. This is not a
cryptographic signature: the reviewed commit is the trust anchor. An
operator-held signing key would provide a stronger follow-up.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from .server import ToolDescription

PINNED_MANIFEST_PATH: Final[Path] = Path(__file__).with_name("mcp-tools.manifest.json")


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


def load_pinned_manifest(path: Path | None = None) -> dict[str, Any]:
    """Load the committed manifest and reject malformed entries."""
    path = path or PINNED_MANIFEST_PATH
    try:
        manifest: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"tool manifest is invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("tool manifest must be an object")
    for field in ("version", "server"):
        if not isinstance(manifest.get(field), str):
            raise ValueError(f"tool manifest {field} must be a string")
    entries = manifest.get("tools")
    if not isinstance(entries, list):
        raise ValueError("tool manifest tools must be a list")
    names: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"tool manifest tools[{index}] must be an object")
        name = entry.get("name")
        if not isinstance(name, str):
            raise ValueError(f"tool manifest tools[{index}].name must be a string")
        if name in names:
            raise ValueError(f"tool manifest has duplicate name: {name}")
        names.add(name)
        tool_hash = entry.get("description_sha256")
        if not isinstance(tool_hash, str) or re.fullmatch(r"[0-9a-f]{64}", tool_hash) is None:
            raise ValueError(f"tool manifest {name} has invalid description_sha256")
    return manifest


def manifest_drift(tools: Sequence[ToolDescription], pinned: dict[str, Any]) -> list[str]:
    """Describe differences between live tools and the committed pin."""
    live = render_well_known_manifest(list(tools))
    drift: list[str] = []
    for field in ("version", "server"):
        if pinned.get(field) != live[field]:
            drift.append(f"{field}: pinned {pinned.get(field)} != live {live[field]}")
    live_hashes = {entry["name"]: entry["description_sha256"] for entry in live["tools"]}
    pinned_hashes = {
        entry["name"]: entry["description_sha256"] for entry in pinned["tools"]
    }
    for name, live_hash in live_hashes.items():
        if name not in pinned_hashes:
            drift.append(f"{name}: live tool absent from pin")
        elif pinned_hashes[name] != live_hash:
            drift.append(f"{name}: pinned {pinned_hashes[name][:12]} != live {live_hash[:12]}")
    for name in sorted(pinned_hashes.keys() - live_hashes.keys()):
        drift.append(f"{name}: pinned tool has no live tool")
    return drift


def write_pinned_manifest(
    tools: Sequence[ToolDescription], path: Path = PINNED_MANIFEST_PATH
) -> None:
    """Write the canonical manifest in the committed format."""
    manifest = render_well_known_manifest(list(tools))
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the pinned MCP tool manifest")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="regenerate the committed pin")
    action.add_argument("--check", action="store_true", help="check live tools against the pin")
    args = parser.parse_args(argv)
    from .server import CANONICAL_TOOLS

    if args.write:
        write_pinned_manifest(CANONICAL_TOOLS)
        print(PINNED_MANIFEST_PATH)
        return 0
    try:
        pinned = load_pinned_manifest()
    except (OSError, ValueError) as exc:
        print(f"tool manifest unreadable: {exc}", file=sys.stderr)
        return 1
    drift = manifest_drift(CANONICAL_TOOLS, pinned)
    if drift:
        for line in drift:
            print(line, file=sys.stderr)
        return 1
    print("mcp tool manifest in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
