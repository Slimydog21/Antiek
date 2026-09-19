#!/usr/bin/env python3
"""Ratchet graph investigation authority and its semantic table inventory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_INVENTORY = Path(__file__).with_name("baselines") / "graph_tenancy_inventory.json"
_BASELINE = Path(__file__).with_name("baselines") / "graph_tenancy_sql.json"
_SEARCH_ROOTS = ("interfaces", "middleware", "orchestration", "roles", "runtime", "substrate")
_SQL_EXEMPT = frozenset({"substrate/legal_gate/read.py"})
_SQL_VERB = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
_CANONICAL_FIELDS = frozenset({"account_digest", "investigation_digest"})


def _schema_sql(schema_path: Path) -> str:
    tree = ast.parse(schema_path.read_text(encoding="utf-8"), filename=str(schema_path))
    chunks: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if (
            any(name.startswith("ANTIEK_GRAPH_SCHEMA_") and name.endswith("_SQL") for name in names)
            and isinstance(node.value.value, str)
        ):
            chunks.append(node.value.value)
    return "\n".join(chunks)


def investigation_tables(schema_path: Path) -> set[str]:
    sql = _schema_sql(schema_path)
    result: set[str] = set()
    for match in _CREATE_TABLE.finditer(sql):
        opening = sql.find("(", match.end())
        if opening < 0:
            raise ValueError("graph schema table declaration is malformed")
        depth = 0
        quoted = False
        closing = -1
        index = opening
        while index < len(sql):
            character = sql[index]
            if not quoted and sql[index : index + 2] == "--":
                newline = sql.find("\n", index + 2)
                index = len(sql) if newline < 0 else newline + 1
                continue
            if character == "'":
                if quoted and index + 1 < len(sql) and sql[index + 1] == "'":
                    index += 2
                    continue
                quoted = not quoted
            elif not quoted and character == "(":
                depth += 1
            elif not quoted and character == ")":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
            index += 1
        if closing < 0:
            raise ValueError("graph schema table declaration is malformed")
        if re.search(r"\binvestigation_id\b", sql[opening:closing], re.IGNORECASE):
            result.add(match.group(1).lower())
    return result


def _read_inventory(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tables = payload.get("tables")
    if payload.get("version") != 1 or not isinstance(tables, dict):
        raise ValueError("graph tenancy inventory is invalid")
    required = {"domain", "authority", "rationale"}
    for table, record in tables.items():
        if (
            not isinstance(table, str)
            or not isinstance(record, dict)
            or set(record) != required
            or record.get("authority")
            not in {"shared_or_owner", "composite_required", "composite_when_bound"}
            or not all(isinstance(record.get(key), str) and record[key] for key in required)
        ):
            raise ValueError("graph tenancy inventory is invalid")
    return tables


def inventory_errors(schema_path: Path, inventory_path: Path) -> list[str]:
    actual = investigation_tables(schema_path)
    declared = set(_read_inventory(inventory_path))
    errors: list[str] = []
    if missing := sorted(actual - declared):
        errors.append(f"unclassified investigation tables: {','.join(missing)}")
    if stale := sorted(declared - actual):
        errors.append(f"stale graph tenancy classifications: {','.join(stale)}")
    return errors


def _literal_text(node: ast.AST) -> str:
    return " ".join(
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    )


class _SqlInventory(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.scope = ["<module>"]
        self.sites: Counter[str] = Counter()

    def _visit_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self.scope.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scope(node)

    def visit_Call(self, node: ast.Call) -> None:
        is_execute = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"execute", "executemany"}
            and bool(node.args)
        )
        if not is_execute:
            self.generic_visit(node)
            return
        # Inspect only the SQL argument. Walking an enclosing statement also
        # absorbs DTO keys, docstrings, and nested queries, producing both
        # false positives and duplicate counts.
        sql = " ".join(_literal_text(node.args[0]).split())
        lowered = sql.lower()
        if not _SQL_VERB.search(sql) or "investigation_id" not in lowered:
            self.generic_visit(node)
            return
        scoped = all(field in lowered for field in _CANONICAL_FIELDS)
        kind = "composite_graph_sql" if scoped else "display_only_graph_sql"
        canonical = "\0".join(
            (self.relative_path, ".".join(self.scope), kind, sql.upper())
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:20]
        self.sites[f"{kind}:{self.relative_path}:{'.'.join(self.scope)}:{digest}"] += 1
        self.generic_visit(node)


def sql_inventory(root: Path) -> Counter[str]:
    sites: Counter[str] = Counter()
    for relative_root in _SEARCH_ROOTS:
        production_root = root / relative_root
        if not production_root.exists():
            continue
        for path in sorted(production_root.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            if relative in _SQL_EXEMPT:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            visitor = _SqlInventory(relative)
            visitor.visit(tree)
            sites.update(visitor.sites)
    return sites


def _read_baseline(path: Path) -> Counter[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("sites"), dict):
        raise ValueError("graph tenancy SQL baseline is invalid")
    return Counter({key: int(value) for key, value in payload["sites"].items()})


def new_sql_sites(root: Path, baseline_path: Path) -> Counter[str]:
    current = Counter(
        {site: count for site, count in sql_inventory(root).items() if site.startswith("display_only_graph_sql:")}
    )
    return current - _read_baseline(baseline_path)


def write_baseline(root: Path, baseline_path: Path) -> None:
    sites = {
        site: count
        for site, count in sql_inventory(root).items()
        if site.startswith("display_only_graph_sql:")
    }
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps({"version": 1, "sites": dict(sorted(sites.items()))}, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=_REPO)
    parser.add_argument("--schema", type=Path, default=_REPO / "substrate/graph/schema.py")
    parser.add_argument("--inventory", type=Path, default=_INVENTORY)
    parser.add_argument("--baseline", type=Path, default=_BASELINE)
    parser.add_argument("--regenerate", action="store_true")
    args = parser.parse_args(argv)
    if args.regenerate:
        write_baseline(args.root, args.baseline)
        print(f"wrote graph tenancy SQL baseline: {sum(_read_baseline(args.baseline).values())} sites")
        return 0
    errors = inventory_errors(args.schema, args.inventory)
    additions = new_sql_sites(args.root, args.baseline)
    if errors or additions:
        print("Graph tenancy boundary violations:")
        for error in errors:
            print(f"  {error}")
        for site, count in sorted(additions.items()):
            print(f"  {site} (+{count})")
        return 1
    print("OK: graph tenancy table inventory complete and display-only SQL debt did not grow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
