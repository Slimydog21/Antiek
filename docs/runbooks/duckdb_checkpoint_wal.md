# Runbook · DuckDB checkpoint / WAL

**Owner:** substrate
**Last verified:** 2026-05-24

## Symptom

One or more of:

- DuckDB queries report `Catalog Error: Table with name <X> does not exist`
  for a table the schema obviously defines.
- A previously-committed write doesn't appear in a fresh connection.
- File size on disk balloons unexpectedly between checkpoints.
- `PRAGMA database_size` reports a much smaller value than the file
  on disk.

## Likely cause

DuckDB uses a Write-Ahead Log (WAL) for durability. The data is
considered committed once the WAL fsyncs, but it doesn't migrate into
the main file until CHECKPOINT (explicit or on close). Most "table
doesn't exist" symptoms in Antiek are NOT WAL issues — they're missing
migrations (e.g., the `write_log` table was added late; pre-migration
substrates see "Catalog Error" until `migrate_v7_write_log.py` runs).

## Quick diagnostics

```bash
# Is the WAL present?
ls -la <db>.duckdb.wal

# Has the schema been migrated to v7+?
.venv/bin/python -c "
import duckdb
con = duckdb.connect('<path>.duckdb', read_only=True)
print(con.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall())
"

# Force a checkpoint (only against a closed-but-writable substrate).
.venv/bin/python -c "
from runtime.db_lock import connect_write
with connect_write('<path>', purpose='manual_checkpoint') as con:
    con.execute('CHECKPOINT')
"
```

## Root-cause path

For "table doesn't exist" symptoms:

1. The most common cause is missing migration, not WAL drift. Check
   `substrate/schemas/` or the relevant module's `_apply_migrations`
   path.
2. The `write_log` table specifically is created by
   `migrate_v7_write_log.py`. When `db_lock`'s observability layer
   tries to log to a substrate where that migration hasn't run, it
   swallows the error with a stderr breadcrumb (`db_lock: write_log
   insert failed (non-fatal)`). This is by design — the main pipeline
   must NEVER fail because the log table is missing.

For "committed write not visible" symptoms:

1. DuckDB readers see the WAL. A reader opened BEFORE the writer
   committed will not see the new rows until it refreshes (closes/
   reopens). Use `connect_read` per-query, not a long-lived reader.
2. If the writer crashed without releasing the flock cleanly, the WAL
   may contain uncheckpointed pages. Next writer's CHECKPOINT will
   merge them. The kernel-released flock semantics (db_lock I3) mean
   no data loss; just delayed materialization.

For "file size balloons" symptoms:

1. DuckDB's WAL doesn't auto-truncate between writes. Long-running
   writers accumulate WAL pages. Solution: periodic explicit CHECKPOINT
   in the writer's hot path (e.g., every N events in the autoresearch
   loop).

## Mitigation

| Cause | Mitigation |
|---|---|
| Missing migration | Run the relevant migration: `python -m substrate.schemas.migrate_v7_write_log <db>` |
| Long-lived reader sees stale state | Open a fresh `connect_read` per query |
| WAL bloat | Add `con.execute("CHECKPOINT")` to the writer's commit-boundary path |
| Crash without checkpoint | Next writer will recover. If urgent: open + close a write context with `purpose="manual_checkpoint"` |

## Reference

- DuckDB WAL docs: <https://duckdb.org/docs/internals/storage>
- Migration runner: `substrate/schemas/migrate_*.py`
- db_lock observability: `runtime/db_lock.py::_log_write_event`
- The stderr breadcrumb specifically:
  ```python
  _sys.stderr.write(f"db_lock: write_log insert failed (non-fatal): ...")
  ```

## Worked example

```
db_lock: write_log insert failed (non-fatal): CatalogException:
Catalog Error: Table with name write_log does not exist!
Did you mean "duckdb_logs"?
```

Trace:

1. This is the breadcrumb — it appears once per write on a substrate
   that hasn't run the v7 migration. It's NOT a bug; the main pipeline
   completed successfully.
2. To remove the noise: run `migrate_v7_write_log.py` against the
   substrate. After migration, the breadcrumb disappears and `write_log`
   starts accumulating per-write rows.
3. To suppress entirely (e.g., in CI fresh-DB tests): set
   `ANTIEK_DISABLE_BURN_TELEMETRY=1` — both the burn ledger and the
   write_log emission then no-op.
