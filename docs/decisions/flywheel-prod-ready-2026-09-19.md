# Decision: Restore prod flywheel_ready (honest knowledge.reused)

**Date**: 2026-09-19  
**Status**: accepted  
**Cite**: SPR-11 `_probe_flywheel`; #3118 Loop One reuse; Mini dogfood reuse=18; prod host events at `ANTIEK_EVENT_LOG_DIR`.

## Root cause

Prod `/health` `flywheel_ready=false` / `knowledge_reuse_count=0` was **honest**: zero `knowledge.reused` events in `/home/antiek/.antiek/research_events`. Graph had 18 insights / 24 historical investigations, but last `investigation.start_requested` was **2026-06-24** — before #3118 wired Loop One reuse. Mini was true because spin-research dogfood emitted reuse into its isolated events dir.

Secondary gaps fixed here:
1. systemd sets `ANTIEK_EVENT_LOG_DIR`; `default_events_dir` only read `ANTIEK_RESEARCH_EVENTS_DIR` (same path via `~/.antiek` fallback, but alias was fragile).
2. Out-of-process reuse smoke failed on DuckDB exclusive lock while uvicorn held the file — `maybe_reuse` now falls back to `connect_read`.
3. `/health` memoized the first false forever — re-probe on cooldown while still false so an honest seed can flip without inventing readiness.

## Decision

- Alias env vars; RO fallback; health cooldown re-probe while false.
- Seed one real `knowledge.reused` on prod (ops smoke / Loop One start) — never force the boolean.

## Non-goals

- Faking `flywheel_ready` without an event.
- Replaying historical investigations.

## Consequences

Prod compounding signal becomes live when reuse emits. Next: CLI/Herdr or Lego TP slotting.

## Outcome (2026-09-19 ~12:28 Asia/Riyadh)

- Merged #3177 → tip `0471c4830…`. Deployed Mini + prod (`/opt/antiek`).
- Seeded honest `knowledge.reused` `evt-bf899a87684f-1789809958637` via `maybe_reuse_prior_knowledge_at_start` (RO fallback under API lock; empty unit inject still records reuse per #3118).
- Prod public `/health`: `flywheel_ready=true`, `knowledge_reuse_count=1`, `build_sha=0471c4830…`.
- Mini: tip-aligned, `flywheel_ready=true`, `knowledge_reuse_count=18`.
