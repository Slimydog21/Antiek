"""Concurrent-writer helper for migration race tests.

Attempts short timed writes into feedback_threads while the migration runs.
Logs every successfully inserted thread_id to a sidecar file; records
timeouts and a missing-table stop condition on stdout as KEY=VALUE lines.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb

from runtime.db_lock import WriteLockTimeout, connect_write

INSERT_SQL = """
INSERT INTO feedback_threads (
    thread_id, owner_user_id, investigation_id, artifact_id, artifact_version,
    artifact_content_sha256, artifact_source_sha256, normalization,
    anchor_node_id, anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar,
    anchor_quote, anchor_prefix, anchor_suffix, state, create_operation_id,
    create_request_sha256
) VALUES (?, ?, ?, ?, 1, ?, ?, 'unicode-nfc-v1', 'node-1', ?, 0, 1, 'q', '', '', 'open', ?, ?)
"""


def main() -> int:
    db, prefix, log_path = sys.argv[1], sys.argv[2], sys.argv[3]
    attempts = int(sys.argv[4])
    pauses = (
        [float(value) for value in sys.argv[5].split(",")]
        if len(sys.argv) > 5
        else [0.0]
    )
    log = Path(log_path)
    inserted = 0
    timeouts = 0
    missing_table = False
    for index in range(attempts):
        thread_id = f"{prefix}-{index}"
        try:
            with connect_write(db, purpose="d2-concurrent-writer", timeout_s=0.25) as con:
                con.execute(INSERT_SQL, [
                    thread_id, "load-writer", "inv-load", "art-load",
                    "a" * 64, "b" * 64, "c" * 64, "op-" + thread_id, "d" * 64,
                ])
            inserted += 1
            with log.open("a") as handle:
                handle.write(thread_id + "\n")
        except WriteLockTimeout:
            timeouts += 1
        except duckdb.IOException as exc:
            if "Could not set lock" in str(exc):
                # DuckDB's own cross-process write lock: same exclusion fact.
                timeouts += 1
            else:
                raise
        except Exception as exc:
            if "does not exist" in str(exc) or "not found" in str(exc).lower():
                missing_table = True
                break
            raise

        time.sleep(pauses[index % len(pauses)])
    print(f"inserted={inserted}")
    print(f"timeouts={timeouts}")
    print(f"missing_table={missing_table}")
    return 0 if inserted > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
