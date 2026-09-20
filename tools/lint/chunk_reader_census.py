"""Enumerate SQL chunk readers and require an explicitly reviewed inventory.

This scans tracked Python source, not just occurrences of chunk_text. Each SQL
FROM/JOIN chunks expression (including aliases, wildcard and f-string projections)
and whole-database export must have an audience, disposition and evidence. A source
change invalidates its review even when the function name stays the same.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/diagnostics/research-only-principals/reader-inventory.json"
_RELATION = re.compile(r'\b(?:FROM|JOIN)\s+(?:[\w"]+\.)?["`]?chunks\b|\bEXPORT\s+DATABASE\b', re.I)


def _text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_text(value) if isinstance(value, ast.Constant) else "{dynamic}" for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _text(node.left) + _text(node.right)
    return "{dynamic}"


class _Readers(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.stack: list[str] = []
        self.nodes: list[ast.AST] = []
        self.rows: list[dict[str, str | int]] = []

    def visit_Expr(self, node: ast.Expr) -> None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return  # docstrings describe readers; they are not executed SQL
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        self.nodes.append(node)
        self.generic_visit(node)
        self.nodes.pop()
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _expression(self, node: ast.AST) -> None:
        sql = _text(node)
        if _RELATION.search(sql) or sql.strip().lower() == "chunks":
            normalized = " ".join(sql.split())
            function = ".".join(self.stack) or "<module>"
            digest = hashlib.sha256(normalized.encode()).hexdigest()
            self.rows.append({"path": self.path, "function": function,
                              "line": getattr(node, "lineno", 0), "sql": normalized, "sha256": digest,
                              "function_sha256": hashlib.sha256(ast.dump(self.nodes[-1] if self.nodes else node, include_attributes=False).encode()).hexdigest()})
        else:
            self.generic_visit(node)

    visit_Constant = _expression
    visit_JoinedStr = _expression
    visit_BinOp = _expression


def census(root: Path = ROOT) -> list[dict[str, str | int]]:
    paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"], cwd=root, text=True).splitlines()
    rows: list[dict[str, str | int]] = []
    for path in sorted(set(paths)):
        if path.startswith(("tests/", "benchmarks/")) or "/tests/" in path:
            continue
        visitor = _Readers(path)
        visitor.visit(ast.parse((root / path).read_text(), filename=path))
        rows.extend(visitor.rows)
    return rows


def key(row: dict[str, str | int]) -> tuple[str, str, str, str]:
    return str(row["path"]), str(row["function"]), str(row["sha256"]), str(row["function_sha256"])


def check() -> list[str]:
    inventory = json.loads(INVENTORY.read_text())
    expected = inventory["sql_readers"]
    current = {key(row) for row in census()}
    reviewed = {key(row) for row in expected}
    failures = [f"Unreviewed chunk reader: {item}" for item in sorted(current - reviewed)]
    failures.extend(f"Stale reader review: {item}" for item in sorted(reviewed - current))
    for row in expected:
        for field in ("audience", "disposition", "evidence"):
            if not row.get(field):
                failures.append(f"Missing {field}: {key(row)}")
    for path, digest in inventory.get("source_dependencies", {}).items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            failures.append(f"Changed reader dependency needs review: {path}")
    return failures


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        errors = check()
        print("\n".join(errors) if errors else "Chunk-reader inventory matches source")
        raise SystemExit(bool(errors))
    print(json.dumps(census(), indent=2))
