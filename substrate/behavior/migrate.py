"""CLI for the behavior-store migration runner.

Usage:

    python -m substrate.behavior.migrate --apply
    python -m substrate.behavior.migrate --db-path /tmp/x.duckdb --apply

Idempotent. The --apply flag is required so the bare command (no
flags) is a no-op rather than an accidental DDL run.
"""

from __future__ import annotations

import argparse
import sys

import duckdb

from .schema import (
    MIGRATION_FILES,
    default_db_path,
    init_behavior_schema_at_path,
    list_behavior_tables,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Apply behavior-store DDL migrations (idempotent)."
    )
    p.add_argument(
        "--db-path",
        default=None,
        help=(
            "DuckDB file path. Defaults to ANTIEK_DUCKDB_PATH env var "
            "or substrate.constants.DUCKDB_PATH."
        ),
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Required; without it the command lists migrations and exits.",
    )
    args = p.parse_args(argv)

    db_path = args.db_path or default_db_path()

    if not args.apply:
        print(f"behavior.migrate: pending migrations for {db_path}:")
        for fn in MIGRATION_FILES:
            print(f"  {fn}")
        print("Pass --apply to run them.")
        return 0

    init_behavior_schema_at_path(db_path)
    con = duckdb.connect(db_path, read_only=True)
    try:
        tables = list_behavior_tables(con)
    finally:
        con.close()
    print(f"behavior.migrate: applied to {db_path}")
    for t in tables:
        print(f"  table: {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
