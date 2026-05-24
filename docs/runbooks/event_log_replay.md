# Runbook · event_log replay

**Owner:** substrate
**Last verified:** 2026-05-24

## Symptom

- Graph state in DuckDB doesn't match what `events.jsonl` says happened.
- A query returns zero rows for a node that was clearly created (per
  event_log).
- After a crash, the DuckDB state is "behind" the event_log.

## Likely cause

The substrate keeps two stores:

- **`~/.antiek/events.jsonl`** — append-only event log. SOURCE OF
  TRUTH per `substrate/event_log/README.md`.
- **DuckDB graph tables** — DERIVED state. Replayed from events.

If the derived state lags or diverges, the event_log is canonical and
the derived state is rebuilt. This is exactly the P8-style "derived
data" pattern applied to the graph instead of vectors.

Common drift sources:

1. Crash mid-event: event logged to JSONL (write happens first), then
   the process died before applying the event to DuckDB. Recover on
   restart by replaying events whose IDs aren't present in DuckDB.
2. Schema migration that processes events differently than the live
   path did. Re-replay the affected event range.
3. Manual DuckDB edits (shouldn't happen — see the substrate contract).

## Quick diagnostics

```bash
# How many events are in the log?
wc -l ~/.antiek/events.jsonl

# How many event_ids does DuckDB know about? (depends on schema)
.venv/bin/python -c "
from runtime.db_lock import connect_read
with connect_read('~/.antiek/antiek.duckdb') as con:
    # Adjust to your specific event-id-bearing table.
    print(con.execute('SELECT COUNT(DISTINCT parent_event_id) FROM nodes').fetchone())
"

# Find the highest event_id in the JSONL and compare.
tail -1 ~/.antiek/events.jsonl | jq -r .event_id
```

## Root-cause path

The contract: writes are append-only. Readers consume the JSONL in
stream or batch-query the Parquet compaction. NO code path outside
`substrate/event_log/` mutates the log.

The substrate intentionally tolerates short-lived divergence: events
are logged BEFORE materialization. If the process crashes between log
and materialize, the next process replays from the last applied event.

If you see PERSISTENT divergence:

1. Confirm `events.jsonl` is not write-truncated — `wc -l` should be
   monotonically nondecreasing across snapshots.
2. Check the replay code path of the affected module. The continuous-
   research daemon (`substrate/loop_3/`) and the federation thread
   each have their own replay logic.
3. The Parquet compaction is read-then-write to a new file followed
   by atomic rename. If you see partial Parquet (e.g., 0-byte file),
   the rename was interrupted — restore from JSONL.

## Mitigation

| Cause | Mitigation |
|---|---|
| Crash mid-event | Restart the affected service; it replays from the JSONL automatically. |
| Schema migration drift | Re-run the migration's replay path: it's idempotent. |
| Partial Parquet | `rm` the bad parquet; the next compaction recreates it. |
| Manual DB edit | Don't. If unavoidable, the fix is to replay the entire log into a fresh DuckDB file. |

## Reference

- README: `substrate/event_log/README.md`
- Schema: `substrate/schemas/events.py` (Event, ActionType,
  per-action payloads)
- Replay points: `substrate/loop_3/`, `substrate/federation/`
- DDIA P7 / P8 (philosophy doc) — derived data, streaming
  materialization.

## Worked example

```
2026-05-24T08:00:00Z events.jsonl line count: 412334
2026-05-24T08:00:00Z duckdb nodes count: 384112
```

Trace:

1. The JSONL has ~28k more events than DuckDB knows about.
2. The continuous-research daemon (`antiek-continuous-research.service`)
   crashed last night during a long synthesis batch.
3. Restart the daemon: `systemctl restart antiek-continuous-research`.
4. The daemon's startup path replays from the last applied event_id;
   the gap closes in minutes.
5. Verify: `wc -l events.jsonl` and DuckDB node count converge.
