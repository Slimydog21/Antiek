# TurboPuffer health + corpus honesty (no mount flip)

**Date:** 2026-09-19 (Asia/Riyadh)  
**Parent tip:** `1b8623559321ed446265f6a529a0480c61f60852` (#3225)  
**TPuf before:** ~95 · **after:** ~97  
**Does not:** set `production_default_mount=true` / Synquery / G2 / email / invent CPM.

## Forensic TPuf gaps (non-mount)

| Gap | Evidence | Disposition |
|-----|----------|-------------|
| `/health` hid shadow / pointer context / corpus scale | Probe had `shadow_enabled`, `active_pointer_context_ok`, manifest `row_count`; HealthResponse omitted them | **Shipped** — surface on `/health` |
| Indexed corpus scale opaque | Mini active pointer + `{content_hash}.json` carries `row_count` (e.g. 2) but health never reported it | **Shipped** — `turbopuffer_indexed_row_count` |
| TP library grounding stripped query status | `_retrieve_thought_partner_context` dropped `status` / `degraded_reason` | **Shipped** — `library_retrieval_status` (+ degraded reason) on TP response |
| Mount-gated residual | `production_default_mount=false` intentional | **Ops/product** — leave-off only |

## What shipped

1. `probe_turbopuffer_health` → `indexed_row_count` from promote manifest
2. HealthResponse honesty fields: shadow, pointer_context_ok, indexed_row_count, content_hash, duckdb_is_sot, thought_partner_hybrid_wired; mount still read from probe (**False**)
3. Thought Partner returns library retrieval status without inventing hybrid success
4. Tests: row_count sample-verify; mount never True; TP status mapping

## Grade

| Surface | Before | After |
|---------|-------:|------:|
| TurboPuffer | 95 | **97** |
| Composite | ~98.38 | ~98.54 → still **~98** |

Residual TPuf →100: **`production_default_mount` promote** (product ask only) + larger SERVABLE corpus scale when operator rebuilds. Dual structure intact (DuckDB SoT).
