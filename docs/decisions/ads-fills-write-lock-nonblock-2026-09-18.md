# Decision — Ads fills / frame write-lock nonblock

**Date:** 2026-09-18 (Asia/Riyadh)
**Status:** SHIPPED
**Cite:** PR #3121 LazyRW coexist; PR #3153 Speak write_log / invite read path

## Problem

`POST /api/ad/fills` called `connect_write` with the default **300s** flock wait
on the uvicorn event loop. Under `agent_work` / note-taker contention, fills
(and health) hung systematically. Rank 0 honesty (#3156) was live but smoke
could not complete.

## Decision

1. **Read-first exact retry** — `lookup_fill_decision` via `connect_read` /
   LazyRW; no write flock for replays.
2. **Short write cap** — new fills: `timeout_s=2.0`; frame telemetry:
   `timeout_s=5.0`. On timeout → 503 (`ad_fill_writer_busy` /
   `ad_frame_writer_busy`); FE house-degrades.
3. **`asyncio.to_thread`** — lock wait + decide/accrue off the event loop so
   one contended fill cannot wedge the whole worker.
4. **No fake pricing** — ledger remains `$0` / `unpriced` until Rank 0.1.

## Success

Fills no longer systematically hang under write contention.
