#!/usr/bin/env bash
# Weekly analytics plane: curated Parquet export + rebuild analytics.duckdb.
# Safe while antiek.service is running (read-only export).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ANTIEK_PYTHON:-$ROOT/.venv/bin/python}"
DB="${ANTIEK_DUCKDB_PATH:-$HOME/.antiek/antiek.duckdb}"
STAMP="$(date -u +%Y%m%d)"
OUT="${ANTIEK_ANALYTICS_EXPORT_DIR:-$HOME/.antiek/exports/parquet/$STAMP}"
ANALYTICS_DB="${ANTIEK_ANALYTICS_DB:-$HOME/.antiek/analytics.duckdb}"

export ANTIEK_DUCKDB_PATH="$DB"
EVENTS_DIR="${ANTIEK_RESEARCH_EVENTS_DIR:-$HOME/.antiek/research_events}"

"$PY" "$ROOT/scripts/export_analytics_parquet.py" --db "$DB" --out "$OUT"
"$PY" "$ROOT/scripts/export_dispatch_events_parquet.py" \
  --events-dir "$EVENTS_DIR" \
  --out "$OUT/dispatch_calls.parquet"
"$PY" "$ROOT/scripts/rebuild_analytics_duckdb.py" --parquet-dir "$OUT" --out "$ANALYTICS_DB"

echo "analytics plane: export=$OUT db=$ANALYTICS_DB"