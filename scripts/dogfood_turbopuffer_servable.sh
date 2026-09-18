#!/usr/bin/env bash
# Operator dogfood: TurboPuffer shadow → SERVABLE readiness on Mac Mini.
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

echo "== status =="
python -m tools.turbopuffer_shadow status --db "$DB"

echo "== rebuild --dry-run =="
python -m tools.turbopuffer_shadow rebuild --db "$DB" --dry-run

if [[ "${ANTIEK_TURBOPUFFER_DOGFOOD_LIVE:-0}" == "1" ]]; then
  echo "== live rebuild =="
  REBUILD_JSON="$(python -m tools.turbopuffer_shadow rebuild --db "$DB")"
  echo "$REBUILD_JSON"
  MANIFEST="$(python -c "import json,sys; print(json.loads(sys.argv[1])["manifest_path"])" "$REBUILD_JSON")"
  HASH12="$(python -c "import json,sys; print(json.loads(sys.argv[1])["content_hash"][:12])" "$REBUILD_JSON")"
  echo "== promote =="
  python -m tools.turbopuffer_shadow promote --db "$DB" \
    --manifest "$MANIFEST" --confirm "PROMOTE-${HASH12}"
  echo "== query (expect status servable) =="
  python -m tools.turbopuffer_shadow query --db "$DB" \
    --query "government of the people" --include-result-ids
else
  echo "(set ANTIEK_TURBOPUFFER_DOGFOOD_LIVE=1 for rebuild+promote+query)"
fi
