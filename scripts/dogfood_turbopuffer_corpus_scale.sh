#!/usr/bin/env bash
# Scale TurboPuffer SERVABLE index from DuckDB SoT rights-clean corpus.
# Ingests a small Gutenberg PD set (staging→merge OR allow-prod-write),
# backfills embeddings_meta if needed, then turbopuffer sync(+promote).
set -euo pipefail
export PATH="/opt/homebrew/bin:${HOME}/.local/bin:${PATH}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f "${HOME}/Antiek/platform/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${HOME}/Antiek/platform/.env"
  set +a
fi
export ANTIEK_TURBOPUFFER_SERVABLE="${ANTIEK_TURBOPUFFER_SERVABLE:-1}"
DB="${ANTIEK_GRAPH_DB:-${HOME}/.antiek/research_graph.duckdb}"
# Short, high-signal PD spine (Alice, Modest Proposal, Frankenstein, Meditations)
PD_IDS="${ANTIEK_TURBOPUFFER_PD_IDS:-11,1080,84,2680}"
STAGING="${ANTIEK_TURBOPUFFER_STAGING_DB:-/tmp/antiek-pd-tpuf-staging.duckdb}"

echo "== eligible stats (before) =="
python -m tools.turbopuffer_shadow stats --db "$DB" || true

if [[ "${ANTIEK_TURBOPUFFER_DOGFOOD_INGEST:-0}" == "1" ]]; then
  echo "== PD ingest to staging ($PD_IDS) =="
  rm -f "$STAGING"
  python -m tools.run_corpus_ingest \
    --source public_domain --pd-ids "$PD_IDS" --limit 8 \
    --staging-db "$STAGING" --investigation-id inv-tpuf-corpus-scale
  echo "== merge staging → live =="
  python -m tools.merge_staging --staging-db "$STAGING" --live-db "$DB"
  echo "== backfill embeddings_meta (export classes) =="
  python -m tools.backfill_embeddings_meta --db "$DB" --only-export-classes
fi

echo "== eligible stats =="
python -m tools.turbopuffer_shadow stats --db "$DB"

if [[ "${ANTIEK_TURBOPUFFER_DOGFOOD_LIVE:-0}" == "1" ]]; then
  echo "== sync (rebuild if digest changed) =="
  SYNC_JSON="$(python -m tools.turbopuffer_shadow sync --db "$DB")"
  echo "$SYNC_JSON"
  STATUS="$(python -c "import json,sys; print(json.loads(sys.argv[1]).get(\"status\"))" "$SYNC_JSON")"
  if [[ "$STATUS" == "staged" ]]; then
    HASH12="$(python -c "import json,sys; print(json.loads(sys.argv[1])[\"rebuild\"][\"content_hash\"][:12])" "$SYNC_JSON")"
    MANIFEST="$(python -c "import json,sys; print(json.loads(sys.argv[1])[\"rebuild\"][\"manifest_path\"])" "$SYNC_JSON")"
    echo "== promote =="
    python -m tools.turbopuffer_shadow promote --db "$DB" \
      --manifest "$MANIFEST" --confirm "PROMOTE-${HASH12}"
  fi
  echo "== query =="
  python -m tools.turbopuffer_shadow query --db "$DB" \
    --query "government of the people liberty" --include-result-ids
  python -m tools.turbopuffer_shadow status --db "$DB"
else
  echo "(set ANTIEK_TURBOPUFFER_DOGFOOD_INGEST=1 and/or ANTIEK_TURBOPUFFER_DOGFOOD_LIVE=1)"
fi
