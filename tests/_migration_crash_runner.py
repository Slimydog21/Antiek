"""Subprocess runner for real-process kill/resume migration tests.

Exit 0 means the migration completed. A nonzero exit other than 70 means
failure; exit 70 is the deterministic crash injected by
D2_FEEDBACK_V41_CRASH_AFTER at a committed phase boundary.
"""

from __future__ import annotations

import sys

from runtime.db_lock import connect_write
from substrate.feedback.migrations import migrate_feedback_v41


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: _migration_crash_runner.py <duckdb-path>", file=sys.stderr)
        return 2
    with connect_write(sys.argv[1], purpose="d2-v41-kill-resume-test") as con:
        migrate_feedback_v41(con)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
