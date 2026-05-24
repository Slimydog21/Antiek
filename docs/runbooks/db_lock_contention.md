# Runbook · db_lock contention

**Owner:** substrate
**Last verified:** 2026-05-24

## Symptom

```
WriteLockTimeout: Could not acquire write lock on /path/<db>.write.lock within 300s.
Another writer is holding it; inspect with `lsof <db>.write.lock`.
```

Or: an ingest cron / autoresearch loop appears wedged for minutes, then
times out with the message above.

## Likely cause

Two writers raced for the substrate flock and the loser hit the 300s
default timeout (`DEFAULT_TIMEOUT_S` in `runtime/db_lock.py`). The
common scenarios:

1. The daily ingest cron and the weekly monitor cron overlapped.
2. An on-demand research worker started while the continuous-research
   daemon was mid-batch.
3. A crashed writer left its flock held — kernel should have released
   it on FD close, but the sidecar file still has a stamped PID and
   `_stale_pid_check` hasn't run yet.

## Quick diagnostics

```bash
# Who currently holds the flock? (macOS / Linux)
lsof <db>.write.lock | head

# Who STAMPED the sidecar last? (PID + purpose + UTC timestamp)
cat <db>.write.lock

# Is the stamped PID still alive?
kill -0 <PID-from-stamp>; echo $?    # 0 = alive, 1 = dead
```

If `lsof` shows no holder but the sidecar exists: the previous writer
crashed; `_stale_pid_check` will unlink on the next acquire attempt.

If `lsof` shows a live holder with `purpose=ingest` or
`purpose=continuous_research`: cron collision. Not a bug; just busy.

## Root-cause path

The substrate enforces single-writer per `runtime/db_lock.py`. The
invariants are documented in `docs/decisions/db_lock_invariants.md` —
specifically I1 (mutual exclusion) and I2 (bounded wait).

If the symptom is "timeout fires unexpectedly fast" (e.g., 0.4s):

- This used to be a real I2 violation (the timeout path's log-on-fail
  could block 5s waiting on the original holder). SPR-01 of the
  DDIA-execution spec fixed it: `_log_write_event` now accepts
  `_grace_s=0.0` on the timeout path. If you see fast-but-still-too-slow
  timeouts, check that `runtime/db_lock.py` still has the
  `_grace_s=0.0` pass-through in `connect_write`.

If the symptom is "long timeout under load" (cron collision):

- Increase `timeout_s` via the per-call argument — but only if the
  caller is willing to wait. A user-facing ingest should fail fast and
  let the operator retry; a nightly cron should use
  `connect_write_retrying(max_retries=3, retry_delay_s=60.0)`.

## Mitigation

| Cause | Mitigation |
|---|---|
| Cron collision (active holder, busy) | Wait, or schedule the colliding cron to a different window. `connect_write_retrying` for cron entry points. |
| Stale sidecar (no live holder) | Already self-healing — `_stale_pid_check` cleans up on the next acquire. If somehow stuck, `rm <db>.write.lock` is safe IF you've confirmed no live holder. |
| Real I2 regression (timeout fires too fast) | Revert any change to `_log_write_event`'s `_grace_s` handling. The test `tests/test_db_lock_chaos.py::test_acquire_timeout_raises` defends this. |
| Repeated SIGKILL of writers | Stop SIGKILL-ing; use SIGTERM so the cleanup runs. If SIGKILL is forced (OOM-killer), increase the process's memory budget. |

## Reference

- Code: `runtime/db_lock.py`
- Invariants: `docs/decisions/db_lock_invariants.md`
- Chaos test: `tests/test_db_lock_chaos.py`
- Formal spec: `runtime/db_lock_spec.fizz`
- Memory: `project_researchmaxx_duckdb.md` (Quack-swap context)

## Worked example

```
2026-05-23T03:00:00Z INFO  ingest started
2026-05-23T03:05:00Z ERROR WriteLockTimeout: Could not acquire write lock
                            on /home/antiek/.antiek/antiek.duckdb.write.lock
                            within 300s. Another writer is holding it.
```

Trace:

1. `cat /home/antiek/.antiek/antiek.duckdb.write.lock` shows
   `12345 continuous_research 2026-05-23T03:00:00Z` — the daemon is
   holding it.
2. `kill -0 12345` returns 0 — daemon is alive.
3. Cause: legitimate cron collision; daily ingest ran into the
   continuous-research daemon's mid-investigation window.
4. Mitigation: reschedule daily ingest to 02:00, OR switch ingest's
   call site to `connect_write_retrying` so it'll wait through the
   daemon's window instead of failing.
