# Turbopuffer shadow dogfood (operator)

**Status:** CLI + tests only. **Not** on production serving. Do **not** wire talk-to-book to TurboPuffer.

DuckDB remains source of truth. TurboPuffer is a SERVABLE-only secondary index for shadow/bench (`public_domain` / `opt_in_licensed` / `source_declared_open`).

## Prerequisites

- `TURBOPUFFER_API_KEY` in `~/Antiek/platform/.env` (shadow/bench only — last4 on Mini was `E4gf` at dogfood time)
- `ANTIEK_TURBOPUFFER_SHADOW_ENABLED=1` for live rebuild/query
- Optional extra: install `turbopuffer==2.8.0` (pyproject extra `turbopuffer_shadow`)
- Canonical graph: `embeddings_meta` populated for chunks; ≥1 SERVABLE document

## Commands (Mac Mini)

```bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
cd /path/to/Antiek/checkout   # feat/turbopuffer-shadow-benchmark-* worktree
set -a && source ~/Antiek/platform/.env && set +a
export ANTIEK_TURBOPUFFER_SHADOW_ENABLED=1
DB="$HOME/.antiek/research_graph.duckdb"

python -m tools.turbopuffer_shadow rebuild --db "$DB" --dry-run
python -m tools.turbopuffer_shadow rebuild --db "$DB"
# promote uses PROMOTE-<first 12 of content_hash> from rebuild JSON
python -m tools.turbopuffer_shadow promote --db "$DB" \
  --manifest .antiek/turbopuffer-shadow/<content_hash>.json \
  --confirm PROMOTE-<content_hash12>
python -m tools.turbopuffer_shadow query --db "$DB" \
  --query "government of the people" --include-result-ids
```

Successful dogfood (2026-09-17 Asia/Riyadh): rebuild staged 2 Gettysburg fixture rows; promote wrote local pointer; query returned `status: shadow` with fixture chunk ids only.

## Rights

Never reclassify gated radar / `restricted_pending_opt_in` PDFs as public. Export allowlist is code-enforced in the adapter.
