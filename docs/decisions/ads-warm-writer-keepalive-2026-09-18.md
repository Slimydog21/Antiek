# Production — DuckDB warm writer keepalive (2026-09-18)

**Status:** accepted  
**Cite:** `runtime/db_lock.py`; #3121 LazyRW coexist; #3164 lease yield; #3165 note_taker yield.

## Forensic

- Prod DB ~925MB; `duckdb.connect` for RW is ~**6.7–6.8s** every time (DuckDB 1.5.2). Immediate reopen is the same; `threads=1` does not help.
- `write_log.duration_s` starts **after** open, so logged lease/note_taker holds understate true flock occupancy by ~open time.
- After #3164/#3165 yields, residual fill misses are dominated by open thrash under concurrent lease.

## Decision

**In-process warm writer keepalive** (`ANTIEK_WRITE_KEEPALIVE_S`, default **20s**):

1. On successful `LockedConnection.close` (no open txn, no error), park the DuckDB handle **and** flock instead of closing.
2. Next `connect_write` in this process (after process gate) reuses the parked handle — **skips open**.
3. Cross-process writers still serialize on flock while warm; bound by keepalive window.
4. Disabled under `PYTEST_CURRENT_TEST` so lock-release tests stay valid.
5. `write_log` on park uses the warm connection (avoids deadlock re-locking flock).
6. `flush_warm_writers()` for tests / deploy.

Not chosen now: separate agent_work DB (larger blast radius); holding flock forever (blocks deploy verify).

## Follow-ups

- notebook / Thinking Partner / TP anatomy.
- Optional: lower keepalive if deploy schema verify contends.
