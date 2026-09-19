#!/usr/bin/env python3
"""Prevent growth of raw investigation stream and account-unscoped graph access."""

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
_BASELINE = Path(__file__).with_name("baselines") / "investigation_tenancy.json"
_STREAM_CALLEES = frozenset({"trajectory", "emit_typed", "log_event", "seal_investigation"})
_SQL_VERBS = re.compile(r"\b(SELECT|UPDATE|DELETE|INSERT)\b", re.IGNORECASE)
_INVESTIGATION_PREDICATE = re.compile(r"\b(?:WHERE|AND)\b[^;]*\binvestigation_id\b", re.IGNORECASE)
_ACCOUNT_SCOPE = re.compile(r"\b(?:account_digest|owner_user_id|account_id)\b", re.IGNORECASE)


def _callee(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _composite_stream(node: ast.Call) -> bool:
    values = [*node.args, *(keyword.value for keyword in node.keywords)]
    return any(
        isinstance(value, ast.Attribute)
        and value.attr in {"stream_key", "event_stream_id"}
        for value in values
    )


def _literal_text(node: ast.AST) -> str:
    """Conservatively join string literals contained in an expression."""
    return " ".join(
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    )


class _Inventory(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.scope = ["<module>"]
        self.sites: Counter[str] = Counter()
        self.stream_aliases: set[str] = set()

    def _record(self, kind: str, discriminator: str) -> None:
        canonical = "\0".join(
            (self.relative_path, ".".join(self.scope), kind, discriminator)
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:20]
        self.sites[f"{kind}:{self.relative_path}:{'.'.join(self.scope)}:{digest}"] += 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        source = (
            node.value.id
            if isinstance(node.value, ast.Name)
            else node.value.attr
            if isinstance(node.value, ast.Attribute)
            else None
        )
        if source in _STREAM_CALLEES:
            self.stream_aliases.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        callee = _callee(node)
        partial_stream = (
            callee == "partial"
            and bool(node.args)
            and (
                isinstance(node.args[0], ast.Name)
                and node.args[0].id in _STREAM_CALLEES | self.stream_aliases
                or isinstance(node.args[0], ast.Attribute)
                and node.args[0].attr in _STREAM_CALLEES
            )
        )
        getattr_stream = (
            isinstance(node.func, ast.Call)
            and isinstance(node.func.func, ast.Name)
            and node.func.func.id == "getattr"
            and len(node.func.args) >= 2
            and isinstance(node.func.args[1], ast.Constant)
            and node.func.args[1].value in _STREAM_CALLEES
        )
        if (
            callee in _STREAM_CALLEES
            or callee in self.stream_aliases
            or getattr_stream
            or partial_stream
        ) and not _composite_stream(node):
            self._record("raw_stream", callee or "dynamic_stream_access")
        if (
            callee == "format"
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Constant)
            and isinstance(node.func.value.value, str)
            and any(suffix in node.func.value.value for suffix in (".jsonl", ".parquet"))
            and (node.args or node.keywords)
        ):
            self._record("raw_stream_filename", node.func.value.value)
        if callee == "join":
            sql = " ".join(_literal_text(node).split())
            if (
                _SQL_VERBS.search(sql)
                and "investigation_id" in sql.lower()
                and not _ACCOUNT_SCOPE.search(sql)
            ):
                self._record("unscoped_graph_sql", sql.upper())
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        migration_lock_exception = (
            self.relative_path == "substrate/investigation_stream_migration.py"
            and self.scope[-1] == "_migration_locks"
        )
        literal = "".join(
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
        if not migration_lock_exception and any(
            suffix in literal for suffix in (".jsonl", ".parquet")
        ) and any(
            isinstance(value, ast.FormattedValue) for value in node.values
        ):
            self._record("raw_stream_filename", literal)
        sql = " ".join(literal.split())
        if (
            _SQL_VERBS.search(sql)
            and "investigation_id" in sql.lower()
            and not _ACCOUNT_SCOPE.search(sql)
        ):
            self._record("unscoped_graph_sql", sql.upper())
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Add):
            pieces = [
                child.value
                for child in ast.walk(node)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            ]
            sql = " ".join(" ".join(pieces).split())
            if (
                _SQL_VERBS.search(sql)
                and "investigation_id" in sql.lower()
                and not _ACCOUNT_SCOPE.search(sql)
            ):
                self._record("unscoped_graph_sql", sql.upper())
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            sql = " ".join(node.value.split())
            if (
                _SQL_VERBS.search(sql)
                and _INVESTIGATION_PREDICATE.search(sql)
                and not _ACCOUNT_SCOPE.search(sql)
            ):
                normalized = re.sub(r"\s+", " ", sql).strip().upper()
                self._record("unscoped_graph_sql", normalized)


def inventory(root: Path) -> Counter[str]:
    sites: Counter[str] = Counter()
    roots = (root / "interfaces", root / "runtime", root / "substrate")
    for production_root in roots:
        if not production_root.exists():
            continue
        for path in sorted(production_root.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            visitor = _Inventory(relative)
            visitor.visit(tree)
            sites.update(visitor.sites)
    return sites


def _read_baseline(path: Path) -> Counter[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("sites"), dict):
        raise ValueError("investigation tenancy baseline is invalid")
    return Counter({key: int(value) for key, value in payload["sites"].items()})


def new_sites(root: Path, baseline_path: Path) -> Counter[str]:
    current = inventory(root)
    baseline = _read_baseline(baseline_path)
    return current - baseline


def write_baseline(root: Path, baseline_path: Path) -> None:
    sites = inventory(root)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps({"version": 1, "sites": dict(sorted(sites.items()))}, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=_REPO)
    parser.add_argument("--baseline", type=Path, default=_BASELINE)
    parser.add_argument("--regenerate", action="store_true")
    args = parser.parse_args(argv)
    if args.regenerate:
        write_baseline(args.root, args.baseline)
        print(f"wrote redacted baseline: {len(inventory(args.root))} fingerprints")
        return 0
    additions = new_sites(args.root, args.baseline)
    if additions:
        print("Investigation tenancy boundary violations:")
        for site, count in sorted(additions.items()):
            print(f"  {site} (+{count})")
        return 1
    print("OK: no new raw investigation stream or unscoped graph SQL access")
    return 0


if __name__ == "__main__":
    sys.exit(main())
