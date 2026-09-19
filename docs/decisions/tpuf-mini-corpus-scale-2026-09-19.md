# Mini TurboPuffer corpus scale (ops + approx lag honesty)

**Date:** 2026-09-19 (Asia/Riyadh)  
**Parent tip:** `25a86bd30eb3c72aa0e1a08d36f84559eedd7c4f` (#3228)  
**Does not:** set `production_default_mount=true` / Synquery / G2 / email / invent CPM.

## Problem

Mac Mini dogfood `/health` reported `turbopuffer_indexed_row_count=2` (fixture tip) while DuckDB SoT already held hundreds of rights-clean SERVABLE-eligible chunks. Prod already ~4837. Rebuild failed at staging verify because vendor `approx_row_count` lagged at **0** after upsert even when strong sample digest/vectors/FTS passed.

## Ops runbook (Mini)

```bash
# From tip worktree (probe), with platform/.env sourced:
export ANTIEK_GRAPH_DB="${ANTIEK_DUCKDB_PATH:-$HOME/.antiek/research_graph.duckdb}"
export ANTIEK_TURBOPUFFER_SERVABLE=1
export ANTIEK_TURBOPUFFER_MANIFEST_DIR="${ANTIEK_TURBOPUFFER_MANIFEST_DIR:-$HOME/.antiek/turbopuffer-shadow}"

# 1) Cover export allowlist meta (export_ready must become true)
python -m tools.backfill_embeddings_meta --db "$ANTIEK_GRAPH_DB" --only-export-classes

# 2) Optional: grow PD spine then merge (see scripts/dogfood_turbopuffer_corpus_scale.sh)
# ANTIEK_TURBOPUFFER_DOGFOOD_INGEST=1 ANTIEK_TURBOPUFFER_DOGFOOD_LIVE=1 \
#   ./scripts/dogfood_turbopuffer_corpus_scale.sh

# 3) Sync + promote (DuckDB remains SoT; pointer-only promote)
SYNC_JSON="$(python -m tools.turbopuffer_shadow sync --db "$ANTIEK_GRAPH_DB")"
# if status=staged → promote with PROMOTE-<hash12>
# 4) Restart Mini API (scripts/start-shared-duckdb-mac-mini.sh); confirm /health indexed_row_count
```

Rights: only `TURBOPUFFER_INDEX_CONTENT_CLASSES` (public_domain / source_declared_open / opt_in_licensed). Private/gated never indexed.

## Code honesty shipped

- Staging verify: SERVABLE-scale (>100) accepts strong sample when `approx_row_count` is unknown/0 (vendor lag); still fails on **partial** approx after brief poll.
- Dual structure unchanged; `production_default_mount` stays false.

## Grade

| Surface | Before | After (ops+code) |
|---------|-------:|-----------------:|
| TurboPuffer | 97 | **98** (Mini corpus no longer tip-of-fixture; mount still ops residual) |
| Composite | ~98.5 | **~98.5** |

Residual TPuf →100: **`production_default_mount` promote** (Faisal ask) + optional further Mini corpus growth toward prod scale.
