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

## Follow-up (same day)

Prod smoke showed RO-then-RW SAME_FILE races + multi-fd flock wedging.
Flipped to **write-first (2s)** then **read lookup fallback**; house scan capped.

## Follow-up

Prod wedge: concurrent RO lookup + RW open → DuckDB SAME_FILE; multi-fd flock.
Fix: in-process `_FILLS_GATE` + read-first under gate + 2s write cap + house scan cap 32.

## Follow-up 2 — BinderException LazyRW

Prod: `connect_read` raised `BinderException: Unique file handle conflict` (DB already attached RW in uvicorn) — not covered by SAME_FILE string → 500.
Expanded `connect_read` LazyRW fallback for unique-handle / already-attached.

## Follow-up 3 — single open (cold DuckDB ~7s)

Prod bench: `connect_read`/`connect_write` each ~7s on ~900MB store; read-then-write stacked to ~14s → client timeouts. Fills is now **write-only** (one open; `decide_fills` SELECT-replays). Flock timeout 8s → 503.

## Follow-up 4 — dedicated fills executor

Lock stamp showed `agent_work/lease` holding the flock; fills `asyncio.to_thread` starved behind default executor workers. Fills now uses `_FILLS_EXECUTOR` (2 workers).
