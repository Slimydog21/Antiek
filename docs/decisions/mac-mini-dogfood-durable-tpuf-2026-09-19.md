# Decision: Mac Mini dogfood durable TurboPuffer + flywheel across tip-sync

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** `scripts/start-shared-duckdb-mac-mini.sh`; `docs/anti-ek-mac-mini-dogfood.md`;
`docs/decisions/tpuf-tp-hybrid-health-2026-09-19.md`.

## Context

Tip-syncing Mini dogfood to `origin/main` by swapping worktrees left
`turbopuffer_hybrid_ready=false` and `flywheel_ready=false` even when prod
matched tip: the start script defaulted
`ANTIEK_TURBOPUFFER_MANIFEST_DIR` to a **worktree-local** shadow (no
`active.json` after a fresh checkout) and isolated events started empty
(no `knowledge.reused`). Operators had to hand-copy pointer + seed after
every sync — an Execution residual under an otherwise tip-aligned SHA.

## Decision

1. **Shared TurboPuffer shadow** — default
   `ANTIEK_TURBOPUFFER_MANIFEST_DIR=$HOME/.antiek/turbopuffer-shadow`
   (same durability class as shared DuckDB). Override still honored.
2. **Bootstrap once** — if shared lacks `active.json` but the worktree
   shadow has one, copy worktree → shared on start.
3. **Flywheel seed dir** — `~/.antiek/flywheel-seed/*.jsonl` holds
   operator-curated real trajectories that include `knowledge.reused`.
   On start, if isolated events have no reuse evidence, copy seeds in.
   Never invent events; never scan the 2GB shared `research_events/`.
4. **STATUS file** — start script writes `/tmp/antiek-anti-ek/STATUS-shared-duckdb.txt`
   with tip SHA + paths for leave-off forensics.

## Non-goals

- Flipping `turbopuffer_production_default_mount` (product).
- Pointing dogfood events at the full `~/.antiek/research_events` tree
  (boot hang risk — keep isolated).
- Inventing AppLovin / paid CPM.

## Consequences

Mini tip-sync keeps `hybrid_ready` + `flywheel_ready` when the shared
pointer and seed are present. Execution anatomy no longer regresses on
worktree swap.
