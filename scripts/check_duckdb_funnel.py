#!/usr/bin/env python3
"""Enforce DuckDB funnel discipline (docs/duckdb_plane.md L3–L5).

In production layers, ``duckdb.connect`` must not appear outside the
explicit allowlist. Reads use ``runtime.db_lock.connect_read``; writes use
``connect_write``. The only sanctioned raw ``duckdb.connect`` sites are
listed in ``ALLOWLIST_REL`` below.

Exit codes:
  0 — clean
  2 — violations (CI-blocking)
  1 — usage error
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PROD_LAYERS = (
    "substrate",
    "acquisition",
    "middleware",
    "orchestration",
    "interfaces",
    "compounding",
    "processing",
    "runtime",
    "apps",
    "roles",
)

# Relative paths that may call duckdb.connect directly (document each in duckdb_plane §15).
ALLOWLIST_REL: frozenset[str] = frozenset(
    {
        "runtime/db_lock.py",
        "scripts/rebuild_analytics_duckdb.py",
        "scripts/export_dispatch_events_parquet.py",
        "substrate/graph/retrieval_substrate.py",
        "substrate/escape_hatch.py",
    }
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    col: int

    def format_line(self) -> str:
        rel = self.path.relative_to(REPO_ROOT)
        return f"{rel}:{self.line}:{self.col}: raw duckdb.connect outside funnel allowlist"


def _is_duckdb_connect(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "connect":
        return False
    val = func.value
    if isinstance(val, ast.Name) and val.id == "duckdb":
        return True
    if isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name):
        return val.value.id == "duckdb"
    return False


def scan_file(path: Path) -> list[Violation]:
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = None
    if rel is not None and rel in ALLOWLIST_REL:
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except UnicodeDecodeError:
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_duckdb_connect(node):
            out.append(
                Violation(path=path, line=node.lineno, col=node.col_offset + 1)
            )
    return out


def prod_python_files() -> list[Path]:
    files: list[Path] = []
    for layer in PROD_LAYERS:
        root = REPO_ROOT / layer
        if not root.is_dir():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    violations: list[Violation] = []
    for path in prod_python_files():
        violations.extend(scan_file(path))
    if violations:
        for v in violations:
            print(v.format_line(), file=sys.stderr)
        print(
            f"\n{len(violations)} funnel violation(s). "
            "Use connect_read / connect_write per docs/duckdb_plane.md.",
            file=sys.stderr,
        )
        return 2
    print("check_duckdb_funnel: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())