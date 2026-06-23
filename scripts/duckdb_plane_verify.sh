#!/usr/bin/env bash
# Operator + CI: verify DuckDB plane invariants (docs/duckdb_plane.md).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ANTIEK_PYTHON:-${ROOT}/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

echo "== duckdb_plane: funnel L5 =="
"$PY" scripts/check_duckdb_funnel.py

echo "== duckdb_plane: harness boundary =="
"$PY" scripts/check_harness_graph_boundary.py

echo "== duckdb_plane: analytics unit gates =="
"$PY" -m pytest \
  tests/test_check_duckdb_funnel.py \
  tests/test_check_harness_graph_boundary.py \
  tests/test_dispatch_analytics_export.py \
  tests/test_agent_write_purposes.py \
  tests/test_posthog_shim.py \
  tests/test_corpuscrawl_plane_snapshot.py \
  tests/test_burn_report.py \
  tests/test_analytics_export_manifest.py \
  -q --tb=no

echo "DUCKDB_PLANE_VERIFY_OK"