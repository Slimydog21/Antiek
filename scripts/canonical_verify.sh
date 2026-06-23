#!/usr/bin/env bash
# ANT-EXEC-H2V SPR-08 — canonical verification profile (repo root, .venv python).
#
# Subcommands:
#   profile              — print Env Card fields for handoff paste
#   cascade              — hermetic cascade contract + adapter + light route
#   handoff <path.md>    — verify_handoff.ts + audit_agent_session.sh
#   agent-gates          — SPR-03/04/08 unit gates (fast; CI-friendly)
#
# USAGE (from repo root):
#   ./scripts/canonical_verify.sh cascade
#   ./scripts/canonical_verify.sh handoff docs/agent-execution/SPR-01-handoff.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer repo .venv (operator dev); fall back to active interpreter (CI pip install).
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
elif [[ -n "${PYTHON:-}" && -x "${PYTHON}" ]]; then
  PY="${PYTHON}"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "FAIL: no python — create .venv or set PYTHON" >&2
  exit 2
fi

usage() {
  echo "Usage: canonical_verify.sh {profile|cascade|handoff <md>|agent-gates}" >&2
  exit 2
}

cmd_profile() {
  echo "pwd: ${ROOT}"
  echo "python: ${PY}"
  echo "python -V: $("${PY}" -V 2>&1)"
  echo "commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "branch: $(git branch --show-current 2>/dev/null || echo unknown)"
  if [[ -n "${ANTIEK_DUCKDB_PATH:-}" ]]; then
    echo "ANTIEK_DUCKDB_PATH: ${ANTIEK_DUCKDB_PATH}"
  else
    echo "ANTIEK_DUCKDB_PATH: (unset)"
  fi
  echo "CANONICAL_VERIFY_OK: profile"
}

cmd_cascade() {
  echo "== cascade: repro contract =="
  "${PY}" scripts/repro_cascade_decompose_contract.py
  echo "== cascade: DispatchDecomposer regression =="
  "${PY}" -m pytest tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response -q --tb=no
  echo "== cascade: light create-plan route =="
  "${PY}" -m pytest tests/test_cascade_create_plan_light.py -q --tb=no
  echo "== cascade: decomposer call-site audit =="
  bash scripts/audit_decomposer_call_sites.sh
  echo "CANONICAL_VERIFY_OK: cascade"
}

cmd_handoff() {
  local f="${1:?handoff markdown path required}"
  echo "== handoff: schema linter =="
  npx --yes tsx tools/agent/verify_handoff.ts "$f"
  echo "== handoff: session theater grep =="
  bash scripts/audit_agent_session.sh "$f"
  echo "CANONICAL_VERIFY_OK: handoff ($f)"
}

cmd_agent_gates() {
  echo "== agent-gates: vitest handoff linter =="
  (cd apps/reading && npm run test:handoff)
  echo "== agent-gates: duckdb funnel (L5) =="
  "${PY}" scripts/check_duckdb_funnel.py
  echo "== agent-gates: harness graph boundary (§10) =="
  "${PY}" scripts/check_harness_graph_boundary.py
  echo "== agent-gates: duckdb plane pytest slice =="
  "${PY}" -m pytest tests/test_audit_agent_session.py tests/test_canonical_verify.py \
    tests/test_check_duckdb_funnel.py tests/test_agent_write_purposes.py \
    tests/test_corpuscrawl_plane_snapshot.py -q --tb=no
  echo "CANONICAL_VERIFY_OK: agent-gates"
}

main() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    profile) cmd_profile ;;
    cascade) cmd_cascade ;;
    handoff) cmd_handoff "$@" ;;
    agent-gates) cmd_agent_gates ;;
    *) usage ;;
  esac
}

main "$@"