# Decision: Deploy schema verifies are read-only (+ BUILD_SHA sync)

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** #3171–#3173 (stop-before-migrate, keepalive=0, live retries);
ansible live note-taker verify WriteLockTimeout flake on tip `649df5fd2`.

## Context

Live post-restart verifies (`verify_note_taker_schema.py` et al.) used
`connect_write` with a 30s flock timeout. Uvicorn's warm writer still held
the lock after restart, so ansible's 8×5s retries still failed=1 even though
migrate-block verifies (service stopped) were green.

Separately, `ANTIEK_BUILD_SHA` in `/etc/antiek/secrets.env` (EnvironmentFile)
overrode the unit/drop-in tip SHA, so `/health` reported a stale build.

## Decision

1. Schema verify CLIs use **`connect_read`** — they only SELECT/DESCRIBE.
2. After `systemctl stop antiek`, **poll write.lock** until free (30s) before migrate.
3. Deploy syncs tip SHA into **secrets.env** + `build-sha.conf` drop-in.
4. Live verify retries stay (12×5s) for attach races; no longer need write flock.

## Non-goals

- Changing warm-writer keepalive semantics for request DML.
- Flipping `turbopuffer_production_default_mount`.
