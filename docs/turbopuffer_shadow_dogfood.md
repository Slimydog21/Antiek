# Turbopuffer SERVABLE dogfood (operator)

**Status:** CLI + tests. DuckDB remains source of truth. TurboPuffer is a
SERVABLE-only secondary hybrid retrieval index for rights-clean external
chunks (`TURBOPUFFER_INDEX_CONTENT_CLASSES` =
`public_domain` / `opt_in_licensed` / `source_declared_open`).

**Not** the default talk-to-book mount. After `promote`, live queries report
`status: "servable"` (pre-promote: `status: "shadow"`). Private / gated /
`user_owned` / `user_public_contribution` stay DuckDB-only.

## Prerequisites

- `TURBOPUFFER_API_KEY` in `~/Antiek/platform/.env`
- `ANTIEK_TURBOPUFFER_SERVABLE=1` (or `ANTIEK_TURBOPUFFER_SHADOW_ENABLED=1`) for live rebuild/query
- Optional: `ANTIEK_TURBOPUFFER_MAX_ROWS` (default `10000`) for larger SERVABLE rebuilds
- Extra: `turbopuffer==2.8.0` (`turbopuffer_shadow` pyproject extra)
- Canonical graph: `embeddings_meta` populated; ≥1 export-class document

## Commands (Mac Mini)

```bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
cd /path/to/Antiek/checkout
set -a && source ~/Antiek/platform/.env && set +a
export ANTIEK_TURBOPUFFER_SERVABLE=1
DB="$HOME/.antiek/research_graph.duckdb"

python -m tools.turbopuffer_shadow status --db "$DB"
python -m tools.turbopuffer_shadow rebuild --db "$DB" --dry-run
python -m tools.turbopuffer_shadow rebuild --db "$DB"
# promote uses PROMOTE-<first 12 of content_hash> from rebuild JSON
python -m tools.turbopuffer_shadow promote --db "$DB" \
  --manifest .antiek/turbopuffer-shadow/<content_hash>.json \
  --confirm PROMOTE-<content_hash12>
python -m tools.turbopuffer_shadow query --db "$DB" \
  --query "government of the people" --include-result-ids
# expect status: servable after promote
```

Or: `./scripts/dogfood_turbopuffer_servable.sh` (dry-run + status; live rebuild
when `ANTIEK_TURBOPUFFER_DOGFOOD_LIVE=1`).

## Rights

Never reclassify gated radar / `restricted_pending_opt_in` PDFs as public.
Export allowlist is code-enforced via `TURBOPUFFER_INDEX_CONTENT_CLASSES`.
