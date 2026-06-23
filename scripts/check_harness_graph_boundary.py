#!/usr/bin/env python3
"""Harness / conversation CLI must not open the graph DuckDB (duckdb_plane §10).

Scans ``substrate/cli/`` for forbidden graph funnel symbols. Harness effects
on graph state must go through substrate APIs that own ``connect_write``.

Exit 2 on violation.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOT = REPO_ROOT / "substrate" / "cli"

FORBIDDEN_ATTRS: frozenset[str] = frozenset(
    {"connect_write", "connect_read", "connect", "default_db_path"}
)
FORBIDDEN_MODULES: frozenset[str] = frozenset({"duckdb", "runtime.db_lock"})


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    detail: str

    def format_line(self) -> str:
        rel = self.path.relative_to(REPO_ROOT)
        return f"{rel}:{self.line}: harness graph boundary: {self.detail}"


def _scan(tree: ast.AST, path: Path) -> list[Violation]:
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in FORBIDDEN_MODULES or alias.name in FORBIDDEN_MODULES:
                    out.append(Violation(path, node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split(".")[0]
            if base in FORBIDDEN_MODULES or node.module in FORBIDDEN_MODULES:
                out.append(Violation(path, node.lineno, f"from {node.module} import ..."))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_ATTRS:
                qual = getattr(node.func.value, "id", None)
                if qual == "duckdb" and node.func.attr == "connect":
                    out.append(Violation(path, node.lineno, "duckdb.connect(...)"))
                elif node.func.attr in ("connect_write", "connect_read"):
                    out.append(Violation(path, node.lineno, f".{node.func.attr}(...)"))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    violations: list[Violation] = []
    if not SCAN_ROOT.is_dir():
        print("check_harness_graph_boundary: OK (no substrate/cli)")
        return 0
    for path in sorted(SCAN_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except UnicodeDecodeError:
            continue
        violations.extend(_scan(tree, path))
    if violations:
        for v in violations:
            print(v.format_line(), file=sys.stderr)
        return 2
    print("check_harness_graph_boundary: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())