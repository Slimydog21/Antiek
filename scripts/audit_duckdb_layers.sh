#!/usr/bin/env bash
# Mechanical §10 layer audit (docs/duckdb_plane.md).
# Exit 0 only when every layer check passes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ANTIEK_PYTHON:-${ROOT}/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

COST_VIEW="${ROOT}/substrate/coordination/cost_view.py"

FUNNEL_OK=0
HARNESS_OK=0
ENGINE_OK=0
AGENTS_OK=0

print_row() {
  local layer="$1" status="$2" evidence="$3"
  printf "%-28s %-6s %s\n" "$layer" "$status" "$evidence"
}

echo "== duckdb_plane §10 layer audit =="

# Global funnel (L3–L5; CLIs + product write/read paths)
if funnel_out="$("$PY" scripts/check_duckdb_funnel.py 2>&1)"; then
  FUNNEL_OK=1
  funnel_evidence="${funnel_out##*$'\n'}"
  [[ -z "$funnel_evidence" ]] && funnel_evidence="$funnel_out"
else
  funnel_evidence="${funnel_out##*$'\n'}"
  [[ -z "$funnel_evidence" ]] && funnel_evidence="$funnel_out"
fi

# AI Harness (§10 — must not touch graph)
if harness_out="$("$PY" scripts/check_harness_graph_boundary.py 2>&1)"; then
  HARNESS_OK=1
  harness_evidence="${harness_out##*$'\n'}"
  [[ -z "$harness_evidence" ]] && harness_evidence="$harness_out"
else
  harness_evidence="${harness_out##*$'\n'}"
  [[ -z "$harness_evidence" ]] && harness_evidence="$harness_out"
fi

# AI Engine — jsonl/trajectory cost source; no OLTP connect_write
engine_evidence=""
if [[ ! -f "$COST_VIEW" ]]; then
  engine_evidence="missing ${COST_VIEW}"
elif grep -q 'trajectory' "$COST_VIEW" && grep -q 'jsonl' "$COST_VIEW"; then
  if grep -q 'connect_write' "$COST_VIEW"; then
    engine_evidence="cost_view.py must not call connect_write (Engine is E-only cost)"
  else
    ENGINE_OK=1
    engine_evidence="cost_view.py reads trajectory/jsonl; no connect_write"
  fi
else
  engine_evidence="cost_view.py must reference trajectory and jsonl (canonical cost source)"
fi

# AI Agents — purpose registry
if agents_out="$("$PY" -m pytest tests/test_agent_write_purposes.py -q --tb=line 2>&1)"; then
  AGENTS_OK=1
  agents_evidence="$(echo "$agents_out" | tail -n 1)"
else
  agents_evidence="$(echo "$agents_out" | tail -n 3 | tr '\n' ' ')"
fi

funnel_status="FAIL"
[[ "$FUNNEL_OK" -eq 1 ]] && funnel_status="PASS"
harness_status="FAIL"
[[ "$HARNESS_OK" -eq 1 ]] && harness_status="PASS"
engine_status="FAIL"
[[ "$ENGINE_OK" -eq 1 ]] && engine_status="PASS"
agents_status="FAIL"
[[ "$AGENTS_OK" -eq 1 ]] && agents_status="PASS"

echo ""
printf "%-28s %-6s %s\n" "LAYER" "STATUS" "EVIDENCE"
printf "%-28s %-6s %s\n" "-----" "------" "--------"
print_row "Deep Research Workflow" "$funnel_status" "$funnel_evidence (§10 W+R+E; funnel)"
print_row "Read" "$funnel_status" "$funnel_evidence (§10 R; funnel)"
print_row "Write" "$funnel_status" "$funnel_evidence (§10 W+R+E; funnel)"
print_row "Speak" "$funnel_status" "$funnel_evidence (§10 W+R+E; funnel)"
print_row "AI Engine" "$engine_status" "$engine_evidence"
print_row "AI Harness" "$harness_status" "$harness_evidence"
print_row "AI Agents" "$agents_status" "$agents_evidence"

ALL_OK=1
[[ "$FUNNEL_OK" -eq 1 && "$HARNESS_OK" -eq 1 && "$ENGINE_OK" -eq 1 && "$AGENTS_OK" -eq 1 ]] || ALL_OK=0

echo ""
if [[ "$ALL_OK" -eq 1 ]]; then
  echo "AUDIT_DUCKDB_LAYERS_OK"
  exit 0
fi
echo "AUDIT_DUCKDB_LAYERS_FAIL" >&2
exit 1