# Ads / Production — shorten agent_work lease write holds (2026-09-18)

**Status:** accepted  
**Cite:** PR #3111 (`asyncio.to_thread` for agent-work); PR #3112 (arxiv max-lock / yield); ads fills fail-fast #3157–#3162; Rank 0.1 pricing #3163 (no fake cents).

## Forensic (prod)

- `POST /internal/agent-work/lease` polls ~every **21s** (`write_log`).
- Each empty lease still holds the DuckDB write flock ~**10s**: open of ~881MB DB (~6.8s) + work/close (~3.7s logged). **`write_log.duration_s` excludes open** (timer starts after `duckdb.connect`).
- `note_taker/replay_*` (~0.6s logged) fragments free windows between leases.
- `POST /api/ad/fills` waited **8s** then `503 ad_fill_writer_busy` under that duty cycle.
- Empty-lease SQL critical section is ~20ms; hold is dominated by open/close. Default `connect_write` timeout of **300s** could stretch holds further under SAME_FILE wait.

## Decision

1. **Route yield (#3112 class):** after `asyncio.to_thread` returns (lock already released), `await asyncio.sleep(ANTIEK_AGENT_WORK_LOCK_YIELD_S)` default **3.0s** before the HTTP response so the bridge delays its next poll and fills/peers can acquire. Cite #3111: DB work stays off the event loop.
2. **Lease `connect_write` timeout:** `ANTIEK_AGENT_WORK_LEASE_WRITE_TIMEOUT_S` default **25s** (not 300s) — fail the lease rather than monopolize the flock.
3. **Reclaim cap:** `max_reclaim` default **5** per lease (arxiv chunk class); leftovers on the next poll. Do not time-throttle reclaim (expired work must still surface).
4. **Fills wait:** raise `_FILLS_WRITE_TIMEOUT_S` **8 → 15s** so a post-yield free window is usable.

No pricing changes. House fills remain `$0` / `unpriced`.

## Follow-ups

- DuckDB open ~6.8s on 881MB is the residual hold; separate agent_work store or warm writer queue would cut further.
- note_taker replay yield if fills still contend after this ship.
