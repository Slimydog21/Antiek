# Ads / Production — note_taker replay write yield (2026-09-18)

**Status:** accepted  
**Cite:** `roles/note_taker/replay.py`; PR #3164 (lease yield); PR #3112 (arxiv max-lock / yield); fills fail-fast #3157–#3162.

## Forensic (prod)

- `start_replay_recovery` polled every **0.5s** and called `catch_up` per investigation.
- Idle catch_up on completed windows still opened DuckDB **write** for:
  - `note_taker/replay_discovery` (config + `calling→uncertain` UPDATE)
  - `note_taker/replay_discover_window` (SELECT only when row exists)
  - `note_taker/replay_advance` (SELECT; return on `completed`)
- Each open on ~881MB holds flock ~**7s** (`write_log.duration_s` ~0.62s excludes open).
- Interleaved with `agent_work/lease` (~10s holds) → fragmented free windows; fills success ~42% after #3164.

## Decision

1. **Read-mostly idle path:** discovery / discover_window / advance use `connect_read` when no mutation is required; write only for INSERT/UPDATE.
2. **Yield between write sessions:** `ANTIEK_NOTE_TAKER_REPLAY_LOCK_YIELD_S` default **1.0s** after releasing the flock (skipped under `PYTEST_CURRENT_TEST`).
3. **Short write timeout:** `ANTIEK_NOTE_TAKER_REPLAY_WRITE_TIMEOUT_S` default **25s**.
4. **Recovery poll:** default `poll_interval_s` **0.5 → 2.0**; yield between investigations.

Correctness: per-investigation `_replay_lock` still serializes catch_up; fingerprint checks remain; provider call still outside the write lock.

## Follow-ups

- DuckDB open ~6.8s residual; warm writer / separate store.
- TP / notebook / Thinking Partner anatomy.
