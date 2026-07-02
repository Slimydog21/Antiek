#!/usr/bin/env bash
# ANT-EXEC-H2V SPR-08 — canonical verification profile (repo root, .venv python).
#
# Subcommands:
#   profile              — print Env Card fields for handoff paste
#   cascade              — hermetic cascade contract + adapter + light route
#   handoff <path.md>    — verify_handoff.ts + audit_agent_session.sh
#   read-foundation      — Read SPR-01 servable-corpus gate + lock
#   read-library         — Read SPR-02 library browse + no-body catalog gate
#   read-reader          — Read SPR-03 reader surface + structured-block gate
#   read-curate          — Read SPR-04 prompt-to-curate servable-only gate
#   read-ad-border       — Read SPR-05 ad-border slots + impression/accrual gate
#   read-voice-notes     — Read SPR-06 voice-note capture + distillation gate
#   agent-gates          — SPR-03/04/08 unit gates (fast; CI-friendly)
#   deep-research        — ANT-DRL P-22..P-28 hermetic harness (SPR-DRL-02, SPR-DRL-08, SPR-DRL-09)
#   html-transport       — ANT-AHT P-29 ResearchArtifact transport gates
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
  echo "Usage: canonical_verify.sh {profile|cascade|read-foundation|read-library|read-reader|read-curate|read-ad-border|read-voice-notes|handoff <md>|agent-gates|deep-research|html-transport}" >&2
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
  echo "== cascade: edit contract regression =="
  "${PY}" -m pytest \
    tests/test_cascade_planner.py::test_invalid_edits_do_not_mutate_or_reopen_gate \
    tests/test_cascade_planner.py::test_from_dict_clamps_out_of_contract_max_depth \
    tests/test_cascade_api.py::test_invalid_question_edits_are_refused_without_mutating_plan \
    tests/test_cascade_api.py::test_invalid_budget_edits_are_rejected_before_persistence \
    tests/test_cascade_api.py::test_max_depth_cap_value_persists \
    -q --tb=no
  echo "== cascade: parallel orchestration regression =="
  "${PY}" -m pytest \
    tests/test_parallel_orchestration.py::test_steer_routes_to_one_research \
    tests/test_parallel_orchestration.py::test_session_reconstructs_from_event_log \
    tests/test_cascade_api.py::test_steer_endpoint_wiring \
    tests/test_cascade_api.py::test_session_reconstructs_after_eviction \
    -q --tb=no
  echo "== cascade: structural gap detection regression =="
  "${PY}" -m pytest \
    tests/test_gap_detection.py \
    tests/test_speak_drw_gap_source.py \
    -q --tb=no
  echo "== cascade: universal ingest regression =="
  "${PY}" -m pytest tests/test_universal_ingest.py -q --tb=no
  echo "== cascade: glass-box monitor UI regression =="
  (cd apps/reading && npm run test -- src/modes/DeepResearchWorkspace/DeepResearchWorkspace.test.tsx --reporter=dot)
  echo "== cascade: light create-plan route =="
  "${PY}" -m pytest tests/test_cascade_create_plan_light.py -q --tb=no
  echo "== cascade: decomposer call-site audit =="
  bash scripts/audit_decomposer_call_sites.sh
  echo "CANONICAL_VERIFY_OK: cascade"
}

cmd_read_foundation() {
  echo "== read-foundation: servable-corpus legal gate =="
  "${PY}" -m pytest tests/test_book_corpus_gate.py tests/test_contracts_read_lock.py -q --tb=no
  echo "CANONICAL_VERIFY_OK: read-foundation"
}

cmd_read_library() {
  echo "== read-library: catalog endpoint + no-body drift guard =="
  "${PY}" -m pytest tests/test_library_api.py tests/test_servability_drift_guard.py tests/test_contracts_read_lock.py -q --tb=no
  echo "== read-library: Library mode + typed catalog client =="
  (cd apps/reading && npm run test -- \
    src/modes/Library/Library.test.tsx \
    src/components/library/useLibrary.test.ts \
    src/components/library/LibraryView.test.tsx \
    src/components/library/WorkCard.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: read-library"
}

cmd_read_reader() {
  echo "== read-reader: structured-block serve gate =="
  "${PY}" -m pytest tests/test_serve_structured_blocks.py tests/test_contracts_read_lock.py -q --tb=no
  echo "== read-reader: book reader surface =="
  (cd apps/reading && npm run test -- \
    src/modes/Reading/Reading.test.tsx \
    src/modes/Reading/paginateBlocks.test.ts \
    src/modes/Reading/TocPanel.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: read-reader"
}

cmd_read_curate() {
  echo "== read-curate: servable-only curation backend =="
  "${PY}" -m pytest tests/test_book_curate.py tests/test_contracts_read_lock.py -q --tb=no
  echo "== read-curate: curation client + Library re-rank =="
  (cd apps/reading && npm run test -- \
    src/api/books.test.ts \
    src/modes/Library/Library.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: read-curate"
}

cmd_read_ad_border() {
  echo "== read-ad-border: slot model + targeting + impression/accrual backend =="
  "${PY}" -m pytest tests/test_reader_ad_slots.py tests/test_read_ad_escrow.py tests/test_contracts_read_lock.py -q --tb=no
  echo "== read-ad-border: reader rails + impression client =="
  (cd apps/reading && npm run test -- \
    src/api/books.test.ts \
    src/modes/Reading/Reading.test.tsx \
    src/modes/Reading/HouseSlot.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: read-ad-border"
}

cmd_read_voice_notes() {
  echo "== read-voice-notes: transcription + confirmed-note backend =="
  "${PY}" -m pytest tests/test_voice_notes.py tests/test_contracts_read_lock.py -q --tb=no
  echo "== read-voice-notes: reader capture + companion thread =="
  (cd apps/reading && npm run test -- \
    src/api/books.test.ts \
    src/modes/Reading/VoiceNote.test.tsx \
    src/modes/Reading/ReadingCompanion.test.tsx \
    src/modes/Reading/Reading.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: read-voice-notes"
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
  echo "== agent-gates: pytest audit + canonical wrapper =="
  "${PY}" -m pytest tests/test_audit_agent_session.py tests/test_canonical_verify.py -q --tb=no
  echo "CANONICAL_VERIFY_OK: agent-gates"
}

cmd_html_transport() {
  echo "== html-transport: P-29 ANT-AHT bundle =="
  "${PY}" -m pytest \
    tests/test_research_artifact_template.py \
    tests/test_research_artifact_export.py \
    tests/test_research_artifact_hooks.py \
    tests/test_research_artifact_compose.py \
    tests/test_research_artifact_blocks.py \
    tests/test_research_artifact_import.py \
    tests/test_reader_snapshot.py \
    tests/test_artifact_routes.py \
    tests/test_acquisition_urls.py::test_ingest_reader_snapshot_when_flag_set \
    tests/test_acquisition_books.py::test_ingest_reader_snapshot_when_flag_set \
    -q --tb=short
  echo "CANONICAL_VERIFY_OK: html-transport"
}

cmd_deep_research() {
  echo "== deep-research: P-22 Loop 1 E2E =="
  "${PY}" -m pytest tests/test_loop_one_orchestrator.py::test_loop_one_happy_path_emits_completed -q --tb=no
  echo "== deep-research: P-23 invariant negative =="
  "${PY}" -m pytest tests/test_deep_research_complete.py::test_drw_only_trajectory_fails_without_synthesis -q --tb=no
  echo "== deep-research: P-24 session reconstruct =="
  "${PY}" -m pytest tests/test_cascade_session.py -q --tb=no
  echo "== deep-research: P-25 PromotionFunnel serialize =="
  "${PY}" -m pytest tests/test_research_runner.py::test_promotion_funnel_serialized_no_lock_timeout -q --tb=no
  echo "== deep-research: P-26 knowledge.reused (two-run) =="
  "${PY}" -m pytest tests/test_flywheel_reuse.py::test_two_run_contract_gather_emits_knowledge_reused_on_second_start -q --tb=no
  echo "== deep-research: P-27 Exa gather mock E2E =="
  "${PY}" -m pytest tests/test_exa_gather_loop.py -q --tb=short
  echo "== deep-research: P-28 parent-terminal observability =="
  "${PY}" -m pytest tests/test_drw_parent_terminal.py -q --tb=short
  echo "CANONICAL_VERIFY_OK: deep-research"
}

main() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    profile) cmd_profile ;;
    cascade) cmd_cascade ;;
    read-foundation) cmd_read_foundation ;;
    read-library) cmd_read_library ;;
    read-reader) cmd_read_reader ;;
    read-curate) cmd_read_curate ;;
    read-ad-border) cmd_read_ad_border ;;
    read-voice-notes) cmd_read_voice_notes ;;
    handoff) cmd_handoff "$@" ;;
    agent-gates) cmd_agent_gates ;;
    deep-research) cmd_deep_research ;;
    html-transport) cmd_html_transport ;;
    *) usage ;;
  esac
}

main "$@"
