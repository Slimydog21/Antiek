#!/usr/bin/env python3
"""Provenance reference lint for role parsers.

Model-emitted provenance ids must be checked against the canonical ids the
orchestrator supplied. Role parsers that surface evidence-reference fields such
as ``source_chunk_ids`` or ``supporting_chunk_ids`` must route through
``substrate.provenance.validate_ref`` / ``validate_refs``.

Exit 0 = clean; exit 1 = violation, printed as ``path:line``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

_TARGET_FIELDS: frozenset[str] = frozenset({
    "source_chunk_ids",
    "supporting_chunk_ids",
    "chunk_ids",
    "source_event_ids",
    "attribution_region_ids",
    "anchor_block_id",
    "cited_chunk_ids",
    "investigation_id",
    "located_chunk_id",
    "matched_node_id",
    "page_or_frame_id",
    "question_id",
    "question_ids",
    "path_nodes",
    "edge_ids",
    "path_node_ids",
    "path_edge_ids",
})

_BRIDGE_VALIDATED_EXCEPTIONS: frozenset[str] = frozenset({
    # The grounder parser is deliberately a pure response-shape parser; the
    # canonical searched chunk ids exist only in interfaces/research/api/grounding.py,
    # which validates located_chunk_id via substrate.provenance.validate_ref.
    "roles/grounder/parser.py",
})


def _imports_validator(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "substrate.provenance":
            imported = {alias.name for alias in node.names}
            if {"validate_ref", "validate_refs"} & imported:
                return True
    return False


def _calls_validator(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in {"validate_ref", "validate_refs"}:
            return True
        if isinstance(func, ast.Attribute) and func.attr in {"validate_ref", "validate_refs"}:
            return True
    return False


def _target_field_sites(tree: ast.Module) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in _TARGET_FIELDS:
            out.append((node.lineno, node.arg))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in _TARGET_FIELDS
        ):
            out.append((node.lineno, node.value))
    return out


def _scan_file(rel: str, path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    sites = _target_field_sites(tree)
    if not sites or (_imports_validator(tree) and _calls_validator(tree)):
        return []

    first_line, first_field = min(sites)
    return [
        f"{rel}:{first_line}: role parser surfaces {first_field!r} without "
        "substrate.provenance.validate_ref(s)"
    ]


def find_violations(root: Path = _REPO) -> list[str]:
    out: list[str] = []
    roles_dir = root / "roles"
    if not roles_dir.exists():
        return out
    for path in sorted(roles_dir.glob("*/parser.py")):
        rel = path.relative_to(root).as_posix()
        if rel in _BRIDGE_VALIDATED_EXCEPTIONS:
            continue
        out.extend(_scan_file(rel, path))
    return sorted(out)


def main() -> int:
    violations = find_violations()
    if violations:
        print("Provenance reference parser violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nModel-emitted provenance refs must be validated with "
            "substrate.provenance.validate_ref(s) before parser output is "
            "emitted or written."
        )
        return 1
    print("OK: role parser provenance refs route through substrate.provenance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
