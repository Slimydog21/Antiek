"""Migration runner for services/library schema.

Mirrors substrate/graph/migrate.py — see that file for the splitter
convention and idempotency posture.

Migrations applied:
- 0001_folders_tags.sql — folders + document_folders + tags +
  document_tags tables (SPR-06).

CLI:
    python -m services.library.migrate --apply --db-path /path/to.db
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable, Optional

import duckdb

_HERE = os.path.dirname(os.path.abspath(__file__))
_MIGRATIONS_DIR = os.path.join(_HERE, "migrations")
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _list_migrations() -> list[str]:
    if not os.path.isdir(_MIGRATIONS_DIR):
        return []
    return sorted(
        os.path.join(_MIGRATIONS_DIR, fn)
        for fn in os.listdir(_MIGRATIONS_DIR)
        if fn.endswith(".sql")
    )


def _strip_sql_comments(chunk: str) -> str:
    out_lines: list[str] = []
    for line in chunk.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines).strip()


def _split_statements(sql_text: str) -> Iterable[str]:
    cleaned = _strip_sql_comments(sql_text)
    for raw in cleaned.split(";"):
        stmt = raw.strip()
        if stmt:
            yield stmt


def _is_already_exists_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "already exists" in msg or "duplicate" in msg


def apply(db_path: Optional[str] = None) -> dict[str, int]:
    if db_path is None:
        db_path = os.environ.get("ANTIEK_DB_PATH", "antiek.duckdb")
    results: dict[str, int] = {}
    for path in _list_migrations():
        fn = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            sql_text = f.read()
        applied = 0
        with duckdb.connect(db_path) as conn:
            for stmt in _split_statements(sql_text):
                try:
                    conn.execute(stmt)
                    applied += 1
                except (duckdb.CatalogException, duckdb.ParserException) as exc:
                    if _is_already_exists_error(exc):
                        applied += 1
                    else:
                        raise
        results[fn] = applied
    return results


def _main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--db-path", type=str, default=None)
    args = p.parse_args(argv)
    if not args.apply:
        p.print_usage()
        return 2
    try:
        result = apply(db_path=args.db_path)
    except Exception as exc:
        print(f"services/library migrate failed: {exc}", file=sys.stderr)
        return 1
    for fn, n in result.items():
        print(f"applied {fn}: {n} statements")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
