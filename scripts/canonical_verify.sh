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
#   read-rabbit-hole     — Read SPR-07 conversational rabbit-hole + voice replies
#   read-passage-research — Read SPR-08 research-from-passage gate
#   read-ad-escrow       — Read SPR-09 rights-holder escrow accrual gate
#   write-outline-block  — Write SPR-01 outline-block model + provenance gate
#   write-edit-capture   — Write SPR-02 edit trajectory capture + G8 gate
#   write-block-repository — Write SPR-03 folders/search/drag provenance gate
#   write-structured-editor — Write SPR-04 TipTap block editor + locator gate
#   write-brainstorm-interview — Write SPR-05 brainstorm drivers + section gate
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
  echo "Usage: canonical_verify.sh {profile|cascade|read-foundation|read-library|read-reader|read-curate|read-ad-border|read-voice-notes|read-rabbit-hole|read-passage-research|read-ad-escrow|write-outline-block|write-edit-capture|write-block-repository|write-structured-editor|write-brainstorm-interview|handoff <md>|agent-gates}" >&2
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
  echo "== read-ad-border: slot model + targeting backend =="
  "${PY}" -m pytest tests/test_reader_ad_slots.py tests/test_contracts_read_lock.py -q --tb=no
  echo "== read-ad-border: reader rails + impression client =="
  (cd apps/reading && npm run test -- \
    src/api/books.test.ts \
    src/modes/Reading/Reading.test.tsx \
    src/modes/Reading/HouseSlot.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: read-ad-border"
}

cmd_read_ad_escrow() {
  echo "== read-ad-escrow: rights-holder accrual + payout gate backend =="
  "${PY}" -m pytest tests/test_read_ad_escrow.py tests/test_contracts_read_lock.py -q --tb=no
  echo "== read-ad-escrow: impression client + reader flush =="
  (cd apps/reading && npm run test -- \
    src/api/books.test.ts \
    src/modes/Reading/Reading.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: read-ad-escrow"
}

cmd_write_outline_block() {
  echo "== write-outline-block: model + invariants + provenance backend =="
  "${PY}" -m pytest \
    tests/test_outline_block.py \
    tests/test_write_routes.py \
    tests/test_speak_write_composer.py \
    tests/test_contracts_write_lock.py \
    -q --tb=no
  echo "CANONICAL_VERIFY_OK: write-outline-block"
}

cmd_write_edit_capture() {
  echo "== write-edit-capture: structured edit events + trajectory harvest =="
  "${PY}" -m pytest tests/test_edit_capture.py tests/test_contracts_write_lock.py -q --tb=no
  echo "== write-edit-capture: editor diff, locator, and capture-not-train UI =="
  (cd apps/reading && npm run test -- \
    src/modes/Write/Editor/editCapture.test.ts \
    src/modes/Write/Editor/locator.test.ts \
    src/modes/Write/EditCapture.test.ts \
    src/modes/Write/Outline.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: write-edit-capture"
}

cmd_write_block_repository() {
  echo "== write-block-repository: folders/search backend + route surface =="
  "${PY}" -m pytest \
    tests/test_block_repository.py \
    tests/test_write_routes.py \
    tests/test_contracts_write_lock.py \
    -q --tb=no
  echo "== write-block-repository: typed client + repository UI + drag provenance =="
  (cd apps/reading && npm run test -- \
    src/modes/Write/writeApi.test.ts \
    src/modes/Write/Repository/Repository.test.tsx \
    src/modes/Write/Repository/dragToOutline.test.ts \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: write-block-repository"
}

cmd_write_structured_editor() {
  echo "== write-structured-editor: structured editor lock =="
  "${PY}" -m pytest tests/test_contracts_write_lock.py -q --tb=no
  echo "== write-structured-editor: TipTap adapter, locators, edit stream, draft mount =="
  (cd apps/reading && npm run test -- \
    src/modes/Write/Editor/tiptapAdapter.test.ts \
    src/modes/Write/Editor/locator.test.ts \
    src/modes/Write/Editor/editCapture.test.ts \
    src/modes/Write/Outline.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: write-structured-editor"
}

cmd_write_brainstorm_interview() {
  echo "== write-brainstorm-interview: brainstorm drivers + section-owned blocks =="
  "${PY}" -m pytest \
    tests/test_brainstorm_interview.py \
    tests/test_write_routes.py \
    tests/test_contracts_write_lock.py \
    -q --tb=no
  echo "== write-brainstorm-interview: client, bounded clarify loop, section UI =="
  (cd apps/reading && npm run test -- \
    src/modes/Write/writeApi.test.ts \
    src/modes/Write/Brainstorm/clarifyLoop.test.ts \
    src/modes/Write/Brainstorm/IdeaDump.test.tsx \
    src/modes/Write/Outline.test.tsx \
    src/modes/Write/WriteHome.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: write-brainstorm-interview"
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

cmd_read_rabbit_hole() {
  echo "== read-rabbit-hole: TTS + gated book-QA backend =="
  "${PY}" -m pytest \
    tests/test_tts_voice_reply.py \
    tests/test_book_qa_meta_reading.py::test_talk_to_book_answer_cites_pages \
    tests/test_book_qa_meta_reading.py::test_talk_to_book_cannot_cite_withheld_region \
    tests/test_book_qa_meta_reading.py::test_talk_to_book_no_extractable_text_fails_gracefully \
    tests/test_book_qa_meta_reading.py::test_talk_to_book_approximate_page_is_labelled \
    tests/test_contracts_read_lock.py \
    -q --tb=no
  echo "== read-rabbit-hole: sidecar voice replies + book conversation UI =="
  (cd apps/reading && npm run test -- \
    src/components/AISidecar.test.tsx \
    src/components/SpokenReply.test.tsx \
    src/modes/Reading/TalkToBook.test.tsx \
    src/api/books.test.ts \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: read-rabbit-hole"
}

cmd_read_passage_research() {
  echo "== read-passage-research: gated seed + provenance backend =="
  "${PY}" -m pytest tests/test_passage_research.py tests/test_contracts_read_lock.py -q --tb=no
  echo "== read-passage-research: typed client + reader handoff =="
  (cd apps/reading && npm run test -- \
    src/api/books.test.ts \
    src/modes/Reading/ResearchThis.test.tsx \
    src/modes/Reading/Reading.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: read-passage-research"
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
    read-rabbit-hole) cmd_read_rabbit_hole ;;
    read-passage-research) cmd_read_passage_research ;;
    read-ad-escrow) cmd_read_ad_escrow ;;
    write-outline-block) cmd_write_outline_block ;;
    write-edit-capture) cmd_write_edit_capture ;;
    write-block-repository) cmd_write_block_repository ;;
    write-structured-editor) cmd_write_structured_editor ;;
    write-brainstorm-interview) cmd_write_brainstorm_interview ;;
    handoff) cmd_handoff "$@" ;;
    agent-gates) cmd_agent_gates ;;
    *) usage ;;
  esac
}

main "$@"
