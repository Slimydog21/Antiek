# Runbook · continuous-research daemon

**Owner:** substrate
**Last verified:** 2026-05-24

## Symptom

`antiek-continuous-research.service` is "active (running)" but no new
events landing in `events.jsonl` for hours. Or: the daemon exits
repeatedly with non-zero status; systemd restarts it; the cycle
continues without progress.

## Likely cause

The daemon ships per master-spec §7.3/§7.4 and is the evidentiary-gap
batcher. Common stall causes:

1. **db_lock contention** — the daemon is waiting on the substrate
   flock that another writer (ingest cron, on-demand worker) is
   holding. Manifests as: process state is "blocked," no events
   landing.
2. **Dispatch quota exhaustion** — every LLM call is failing all
   fallback tiers; the daemon enters a backoff cycle.
3. **Embedding model OOM** — the per-call embedding fails repeatedly
   because the sentence-transformers model can't load. systemd
   restart doesn't help (the issue is host memory, not process state).
4. **Network egress blocked** — dispatch calls can't reach the
   provider; verify-tier fallback fails to all tiers; daemon exits.

## Quick diagnostics

```bash
# Status and recent logs.
systemctl status antiek-continuous-research
journalctl -u antiek-continuous-research -n 200 --no-pager

# Is it actually progressing? (Compare events.jsonl line count over time.)
wc -l ~/.antiek/events.jsonl; sleep 60; wc -l ~/.antiek/events.jsonl

# Is db_lock the blocker?
cat ~/.antiek/antiek.duckdb.write.lock
lsof ~/.antiek/antiek.duckdb.write.lock

# Any recent dispatch failures?
.venv/bin/python -c "
from substrate.event_log import recent
for e in recent(action_type='DISPATCH_CALL', limit=10):
    p = e.payload
    if p.get('fallback_chain_index', 0) > 0 or p.get('cost_usd', 0) == 0:
        print(p.get('provider'), p.get('fallback_chain_index'))
"
```

## Root-cause path

The daemon's lifecycle is:

1. Read the next evidentiary gap from the substrate (rubric-driven
   per §14.4).
2. Dispatch the LLM call (synthesis or extraction tier).
3. Append the resulting event to events.jsonl.
4. Materialize into DuckDB graph state.
5. Loop.

A stall is in exactly one of those steps:

- Step 1 stall: the daemon may be querying for gaps without finding
  any. That's NOT a bug — it's "no work to do." Confirm by checking
  rubric output.
- Step 2 stall: dispatch is slow/failing. The fallback-chain runbook
  applies.
- Step 3 stall: disk full, file-handle exhaustion. `df -h`, `lsof | wc`.
- Step 4 stall: db_lock contention. The db_lock-contention runbook
  applies.

## Mitigation

| Cause | Mitigation |
|---|---|
| db_lock contention | Wait, or reschedule the conflicting cron |
| Quota exhaustion | Check provider quotas; bump or stop the daemon temporarily |
| Embedding model OOM | Increase host memory, or switch to a smaller model |
| Network egress | Check Cloudflare Tunnel + outbound DNS |
| No actual work (rubric reports no gaps) | Not a bug; the daemon is idle by design |

To suspend the daemon cleanly:

```bash
systemctl stop antiek-continuous-research
```

To resume:

```bash
systemctl start antiek-continuous-research
```

## Reference

- Code: `substrate/loop_3/` (continuous-research loop)
- Systemd unit: `infrastructure/systemd/antiek-continuous-research.service`
- Spec: master-spec §7.3, §7.4
- Memory: `project_antiek_handoff_2026_05_23.md` (daemon live on prod
  since 2026-05-23)
- Cross-reference: `db_lock_contention.md`, `dispatch_fallback_chain.md`

## Worked example

```
$ systemctl status antiek-continuous-research
   Active: active (running) since Fri 2026-05-23 14:00:00 UTC; 23h ago

$ wc -l ~/.antiek/events.jsonl  # twice, 60s apart
412334 ~/.antiek/events.jsonl
412334 ~/.antiek/events.jsonl  # no progress

$ cat ~/.antiek/antiek.duckdb.write.lock
89234 ingest 2026-05-24T13:05:00Z

$ kill -0 89234 ; echo $?
0  # ingest cron is still running
```

Trace:

1. Daemon is "running" but no new events.
2. JSONL didn't grow in 60s → daemon stalled.
3. db_lock sidecar shows the ingest cron is holding the flock.
4. Cause: cron collision. Daemon's batch is waiting on db_lock.
5. Mitigation: wait. The ingest will release within minutes; the
   daemon resumes on the next acquire. No action needed unless the
   collision is recurrent — then reschedule per the cron's window.
