#!/usr/bin/env python3
"""Semantic ratchet for document/chunk read bypasses outside legal custody."""

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
_BASELINE = Path(__file__).with_name("baselines") / "legal_document_reads.json"
_SQL_READ = re.compile(r"\b(?:FROM|JOIN)\s+(documents|chunks)\b", re.IGNORECASE)
_SKIP_PARTS = frozenset({"tests", ".venv", "node_modules", ".git", "worktrees"})
_EXEMPT = frozenset(
    {
        "substrate/legal_gate/read.py",
        "substrate/legal_gate/admission.py",
        "substrate/legal_gate/history_migration.py",
        "substrate/graph/ops.py",
        "tools/lint/legal_read_check.py",
    }
)
# Sprint ANT-LGL-03 permits a shrinking baseline only for code proven
# unreachable from product execution (for example, a one-shot historic
# migration).  Reachability is the safe default: a new package must not fall
# into an ambiguous "internal" bucket merely because this tuple was not kept
# in sync with the repository layout.
_UNREACHABLE_MIGRATION_PREFIXES: tuple[str, ...] = ()


class _Reads(ast.NodeVisitor):
    def __init__(self, relative: str) -> None:
        self.relative = relative
        self.scope = ["<module>"]
        self.sites: Counter[str] = Counter()
        self.strings: dict[str, str] = {}
        self.unresolved_calls = 0

    def _scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self.scope.append(node.name)
        outer_strings = self.strings
        # Function/class locals must not inherit assignments made in a sibling
        # scope. Keeping a copy preserves genuine module constants while
        # preventing a generic name such as ``sql`` from contaminating the
        # next route's dynamic execute call.
        self.strings = dict(outer_strings)
        for statement in node.body:
            self.visit(statement)
        self.strings = outer_strings
        self.scope.pop()

    visit_FunctionDef = _scope
    visit_AsyncFunctionDef = _scope
    visit_ClassDef = _scope

    def visit_Assign(self, node: ast.Assign) -> None:
        value = self._sql_text(node.value)
        if value is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.strings[target.id] = value
        self.generic_visit(node)

    def _sql_text(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self.strings.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._sql_text(node.left)
            right = self._sql_text(node.right)
            return None if left is None or right is None else left + right
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue):
                    resolved = self._sql_text(value.value)
                    if resolved is None:
                        return None
                    parts.append(resolved)
            return "".join(parts)
        return None

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"execute", "executemany", "sql"}
            and node.args
        ):
            resolved_sql = self._sql_text(node.args[0])
            encoded_sql = resolved_sql or " ".join(
                child.value
                for child in ast.walk(node.args[0])
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            )
            if resolved_sql is None:
                self.unresolved_calls += 1
            tables = sorted({match.lower() for match in _SQL_READ.findall(encoded_sql)})
            if tables:
                kind = "+".join(tables)
                normalized_sql = " ".join(encoded_sql.split()).lower()
                canonical = "\0".join(
                    (self.relative, ".".join(self.scope), kind, normalized_sql)
                )
                digest = hashlib.sha256(canonical.encode()).hexdigest()[:20]
                self.sites[
                    f"{self.relative}:{'.'.join(self.scope)}:read:{kind}:{digest}"
                ] += 1
        self.generic_visit(node)


def inventory(root: Path) -> Counter[str]:
    sites: Counter[str] = Counter()
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if any(part in _SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        if relative in _EXEMPT:
            continue
        visitor = _Reads(relative)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=relative))
        sites.update(visitor.sites)
    return sites


def unresolved_sql_call_count(root: Path) -> int:
    """Count execute-like calls whose SQL cannot be fully statically resolved.

    This is deliberately an honesty metric, not proof those calls touch legal
    tables: computed table names cannot be classified safely by this AST pass.
    """
    count = 0
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if any(part in _SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        if relative in _EXEMPT:
            continue
        visitor = _Reads(relative)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=relative))
        count += visitor.unresolved_calls
    return count


def debt_classes(sites: Counter[str]) -> Counter[str]:
    classes: Counter[str] = Counter()
    for site, count in sites.items():
        path = site.split(":", 1)[0]
        if path.startswith("tools/"):
            kind = "operator_tooling"
        elif path.startswith(_UNREACHABLE_MIGRATION_PREFIXES):
            kind = "unreachable_migration"
        else:
            kind = "product_runtime"
        classes[kind] += count
    return classes


def _read(path: Path) -> Counter[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("sites"), dict):
        raise ValueError("legal read baseline is invalid")
    return Counter({key: int(value) for key, value in payload["sites"].items()})


def _write(root: Path, path: Path) -> None:
    sites = inventory(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "sites": dict(sorted(sites.items()))}, indent=2) + "\n",
        encoding="utf-8",
    )


def errors(root: Path, baseline: Path) -> list[str]:
    current = inventory(root)
    return [
        f"new raw legal read: {site} (+{count})"
        for site, count in sorted((current - _read(baseline)).items())
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=_REPO)
    parser.add_argument("--baseline", type=Path, default=_BASELINE)
    parser.add_argument("--regenerate", action="store_true")
    args = parser.parse_args(argv)
    if args.regenerate:
        _write(args.root, args.baseline)
        print(f"wrote legal read baseline: {sum(_read(args.baseline).values())} sites")
        return 0
    findings = errors(args.root, args.baseline)
    if findings:
        print("Legal read violations:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    frozen = _read(args.baseline)
    classes = debt_classes(frozen)
    class_text = ", ".join(f"{kind}={classes[kind]}" for kind in sorted(classes))
    unresolved = unresolved_sql_call_count(args.root)
    print(
        f"OK: raw legal read debt did not grow ({sum(frozen.values())} frozen; "
        f"{class_text}; unresolved_execute_calls={unresolved})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
