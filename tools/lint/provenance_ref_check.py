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
    "cluster_id",
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

_EXTRA_PARSER_FILES: tuple[str, ...] = (
    # Research bridge gap clustering parses model-emitted question_ids outside
    # roles/*/parser.py, so it belongs under the same provenance-ref guard.
    "substrate/research_bridge/gap.py",
)


def _imports_validator(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "substrate.provenance":
            imported = {alias.name for alias in node.names}
            if {"validate_ref", "validate_refs"} & imported:
                return True
    return False


def _is_validator_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in {"validate_ref", "validate_refs"}
    if isinstance(func, ast.Attribute):
        return func.attr in {"validate_ref", "validate_refs"}
    return False


def _field_gets(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value in _TARGET_FIELDS
        ):
            continue
        out.append((node.lineno, node.args[0].value))
    return out


def _target_field_sites(tree: ast.AST) -> list[tuple[int, str]]:
    return _field_gets(tree)


def _assigned_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return {
            name
            for elt in target.elts
            for name in _assigned_names(elt)
        }
    return set()


def _names_in(tree: ast.AST) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }


def _fields_in(tree: ast.AST) -> set[str]:
    return {
        field
        for _, field in _field_gets(tree)
    }


def _raw_field_aliases(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    assignments: list[tuple[set[str], ast.AST]] = []
    for node in ast.walk(func):
        target_names: set[str]
        value: ast.AST | None
        if isinstance(node, ast.Assign):
            target_names = {
                name
                for target in node.targets
                for name in _assigned_names(target)
            }
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target_names = _assigned_names(node.target)
            value = node.value
        elif isinstance(node, ast.NamedExpr):
            target_names = _assigned_names(node.target)
            value = node.value
        else:
            continue
        if value is None or not target_names:
            continue
        assignments.append((target_names, value))
        for field in _fields_in(value):
            aliases.setdefault(field, set()).update(target_names)
    changed = True
    while changed:
        changed = False
        for target_names, value in assignments:
            names = _names_in(value)
            for field, field_aliases in aliases.items():
                if not names & field_aliases:
                    continue
                before = len(field_aliases)
                field_aliases.update(target_names)
                changed = changed or len(field_aliases) != before
    return aliases


def _validated_fields(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    aliases = _raw_field_aliases(func)
    out: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Call) or not _is_validator_call(node):
            continue
        out.update(_fields_in(node))
        names = _names_in(node)
        for field, field_aliases in aliases.items():
            if names & field_aliases:
                out.add(field)
    return out


def _unvalidated_field_sites(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    validator_imported: bool,
) -> list[tuple[int, str]]:
    sites = _target_field_sites(func)
    if not sites:
        return []
    validated = _validated_fields(func) if validator_imported else set()
    return [
        (line, field)
        for line, field in sites
        if field not in validated
    ]


def _parser_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and "parse" in node.name
    ]


def _scan_file(rel: str, path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    violations: list[str] = []
    validator_imported = _imports_validator(tree)
    for func in _parser_functions(tree):
        sites = _unvalidated_field_sites(func, validator_imported)
        if not sites:
            continue
        first_line, first_field = min(sites)
        violations.append(
            f"{rel}:{first_line}: parser function {func.name!r} surfaces "
            f"{first_field!r} without substrate.provenance.validate_ref(s)"
        )
    return violations


def _parser_files(root: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    roles_dir = root / "roles"
    if roles_dir.exists():
        for path in sorted(roles_dir.glob("*/parser.py")):
            rel = path.relative_to(root).as_posix()
            if rel not in _BRIDGE_VALIDATED_EXCEPTIONS:
                out.append((rel, path))
    for rel in _EXTRA_PARSER_FILES:
        path = root / rel
        if path.exists():
            out.append((rel, path))
    return sorted(out)


def find_violations(root: Path = _REPO) -> list[str]:
    out: list[str] = []
    for rel, path in _parser_files(root):
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
