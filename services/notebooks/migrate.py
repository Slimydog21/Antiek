"""Thin CLI wrapper around ``services.notebooks.schema``.

Lets the verification gate run

    python -m services.notebooks.migrate --apply

against a tmp DB or the default path.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply services.notebooks migrations to a DuckDB file.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=(
            "DuckDB path. Defaults to ANTIEK_DUCKDB_PATH / "
            "substrate.constants.DUCKDB_PATH."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply migrations. Required.",
    )
    args = parser.parse_args(argv)

    if not args.apply:
        parser.print_usage()
        print("note: pass --apply to run migrations.", file=sys.stderr)
        return 2

    # Defer imports until --apply so `--help` doesn't pull in duckdb.
    try:
        from services.notebooks.schema import (
            default_db_path,
            init_notebooks_schema_at_path,
        )
    except ImportError:  # pragma: no cover — direct-script fallback
        _here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
        from services.notebooks.schema import (  # type: ignore[no-redef]
            default_db_path,
            init_notebooks_schema_at_path,
        )

    db_path = args.db_path or default_db_path()
    init_notebooks_schema_at_path(db_path)
    print(f"services.notebooks: migrations applied to {db_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
