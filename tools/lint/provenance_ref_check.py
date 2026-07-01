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


def _is_ref_field(field: str) -> bool:
    return field in _TARGET_FIELDS or field.endswith(("_id", "_ids"))

_EXTRA_PARSER_FILES: tuple[str, ...] = (
    # Research bridge gap clustering parses model-emitted question_ids outside
    # roles/*/parser.py, so it belongs under the same provenance-ref guard.
    "substrate/research_bridge/gap.py",
)


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _qualified_name(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def _validator_call_names(tree: ast.Module) -> frozenset[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "substrate.provenance":
            for alias in node.names:
                if alias.name in {"validate_ref", "validate_refs"}:
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "substrate":
            for alias in node.names:
                if alias.name != "provenance":
                    continue
                local = alias.asname or alias.name
                names.add(f"{local}.validate_ref")
                names.add(f"{local}.validate_refs")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name != "substrate.provenance":
                    continue
                local = alias.asname or "substrate.provenance"
                names.add(f"{local}.validate_ref")
                names.add(f"{local}.validate_refs")
    return frozenset(names)


def _is_validator_call(node: ast.Call, validator_names: frozenset[str]) -> bool:
    return (_qualified_name(node.func) or "") in validator_names


def _field_reads(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and _is_ref_field(node.args[0].value)
        ):
            out.append((node.lineno, node.args[0].value))
            continue
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
            and _is_ref_field(node.slice.value)
        ):
            out.append((node.lineno, node.slice.value))
    return out


def _dict_ref_key_sites(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key in node.keys:
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and _is_ref_field(key.value)
            ):
                out.append((key.lineno, key.value))
    return out


def _target_field_sites(tree: ast.AST) -> list[tuple[int, str]]:
    return _field_reads(tree) + _dict_ref_key_sites(tree)


def _expr_contains_validator_call(
    tree: ast.AST,
    validator_names: frozenset[str],
) -> bool:
    return any(
        isinstance(node, ast.Call) and _is_validator_call(node, validator_names)
        for node in ast.walk(tree)
    )


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


def _assigned_names_in_stmt(stmt: ast.stmt) -> set[str]:
    if isinstance(stmt, ast.Assign):
        return {
            name
            for target in stmt.targets
            for name in _assigned_names(target)
        }
    if isinstance(stmt, ast.AnnAssign):
        return _assigned_names(stmt.target)
    if isinstance(stmt, ast.AugAssign):
        return _assigned_names(stmt.target)
    return set()


def _imported_names_in_stmt(stmt: ast.stmt) -> set[str]:
    if isinstance(stmt, ast.Import):
        return {
            alias.asname or alias.name.split(".", 1)[0]
            for alias in stmt.names
        }
    if isinstance(stmt, ast.ImportFrom):
        return {
            alias.asname or alias.name
            for alias in stmt.names
        }
    return set()


def _validator_imported_names_in_stmt(stmt: ast.stmt) -> set[str]:
    out: set[str] = set()
    if isinstance(stmt, ast.ImportFrom) and stmt.module == "substrate.provenance":
        for alias in stmt.names:
            if alias.name in {"validate_ref", "validate_refs"}:
                out.add(alias.asname or alias.name)
    elif isinstance(stmt, ast.ImportFrom) and stmt.module == "substrate":
        for alias in stmt.names:
            if alias.name == "provenance":
                out.add(alias.asname or alias.name)
    elif isinstance(stmt, ast.Import):
        for alias in stmt.names:
            if alias.name == "substrate.provenance":
                out.add(alias.asname or "substrate")
    return out


def _non_validator_imported_names_in_stmt(stmt: ast.stmt) -> set[str]:
    return _imported_names_in_stmt(stmt) - _validator_imported_names_in_stmt(stmt)


def _module_shadowed_names(tree: ast.Module) -> set[str]:
    return {
        name
        for stmt in tree.body
        for name in (
            _assigned_names_in_stmt(stmt)
            | _non_validator_imported_names_in_stmt(stmt)
        )
    }


def _function_shadowed_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    shadows: set[str] = set()
    args = (
        list(func.args.posonlyargs)
        + list(func.args.args)
        + list(func.args.kwonlyargs)
    )
    if func.args.vararg is not None:
        args.append(func.args.vararg)
    if func.args.kwarg is not None:
        args.append(func.args.kwarg)
    shadows.update(arg.arg for arg in args)
    for node in ast.walk(func):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            shadows.update(_assigned_names_in_stmt(node))
        elif isinstance(node, ast.NamedExpr):
            shadows.update(_assigned_names(node.target))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            shadows.update(_non_validator_imported_names_in_stmt(node))
    return shadows


def _without_shadowed_validator_names(
    validator_names: frozenset[str],
    shadowed_names: set[str],
) -> frozenset[str]:
    return frozenset(
        name
        for name in validator_names
        if name.split(".", 1)[0] not in shadowed_names
    )


def _names_in(tree: ast.AST) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }


def _fields_in(tree: ast.AST) -> set[str]:
    return {
        field
        for _, field in _field_reads(tree)
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


def _validator_aliases(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    validator_names: frozenset[str],
) -> set[str]:
    aliases: set[str] = set()
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
        if _expr_contains_validator_call(value, validator_names):
            aliases.update(target_names)
    changed = True
    while changed:
        changed = False
        for target_names, value in assignments:
            if not (_names_in(value) & aliases):
                continue
            before = len(aliases)
            aliases.update(target_names)
            changed = changed or len(aliases) != before
    return aliases


def _validated_fields(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    validator_names: frozenset[str],
) -> set[str]:
    aliases = _raw_field_aliases(func)
    validator_aliases = _validator_aliases(func, validator_names)
    out: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Call) or not _is_validator_call(node, validator_names):
            continue
        out.update(_fields_in(node))
        names = _names_in(node)
        for field, field_aliases in aliases.items():
            if names & field_aliases:
                out.add(field)
    for node in ast.walk(func):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and _is_ref_field(key.value)
            ):
                continue
            if _expr_contains_validator_call(value, validator_names):
                out.add(key.value)
            elif _names_in(value) & validator_aliases:
                out.add(key.value)
    return out


def _unvalidated_field_sites(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    validator_names: frozenset[str],
) -> list[tuple[int, str]]:
    sites = _target_field_sites(func)
    if not sites:
        return []
    validated = _validated_fields(func, validator_names) if validator_names else set()
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
    validator_names = _validator_call_names(tree)
    module_shadows = _module_shadowed_names(tree)
    for func in _parser_functions(tree):
        effective_validator_names = _without_shadowed_validator_names(
            validator_names,
            module_shadows | _function_shadowed_names(func),
        )
        sites = _unvalidated_field_sites(func, effective_validator_names)
        if not sites:
            continue
        first_lines_by_field: dict[str, int] = {}
        for line, field in sites:
            first_lines_by_field[field] = min(
                line,
                first_lines_by_field.get(field, line),
            )
        for field, line in sorted(first_lines_by_field.items(), key=lambda item: item[1]):
            violations.append(
                f"{rel}:{line}: parser function {func.name!r} surfaces "
                f"{field!r} without substrate.provenance.validate_ref(s)"
            )
    return violations


def _parser_files(root: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    roles_dir = root / "roles"
    if roles_dir.exists():
        for path in sorted(roles_dir.glob("*/parser.py")):
            rel = path.relative_to(root).as_posix()
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
