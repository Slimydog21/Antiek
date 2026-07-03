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
#   write-draft-generation-style — Write SPR-06 creative_writer + style gate
#   write-trace-to-source — Write SPR-07 provenance trace + gated no-leak
#   write-pre-outline-freeform — Write SPR-08 context window promote/generate
#   write-style-conditioning — Write SPR-09 prompt-level style conditioning
#   speak-consent-rights-gate — Speak SPR-01 consent + public publish gate
#   speak-async-voice-interview — Speak SPR-02 async voice-note interview
#   speak-project-invitations — Speak SPR-03 projects + invite links
#   speak-compounding-interviewer — Speak SPR-04 context-conditioned interviewer
#   speak-cross-interviewee-verification — Speak SPR-05 corroboration honesty
#   speak-contributor-economics — Speak SPR-06 contributor escrow economics
#   speak-economics-matrix — Speak SPR-07 publishing-mode economics matrix
#   speak-biography-authoring — Speak SPR-08 biography outline + draft
#   speak-publishing-physical — Speak SPR-09 publish + physical quote
#   drw-reading-surface-transfer — DRW SPR-10 reader-surface ownership transfer
#   unified-substrate-contract-lock — Unified SPR-01 contracts + dependency lock
#   unified-remote-exec-fanout — Unified SPR-02 remote runner + §16 fanout
#   unified-seams-and-collisions — Unified SPR-03 typed seams + collision guards
#   unified-navigation-ia-taxonomy — Unified SPR-04 workflow taxonomy + nav IA
#   unified-coordination-gate-ledger — Unified SPR-05 gate ledger + roadmap
#   unified-thread-navigation — Unified SPR-06 cross-workflow thread navigation
#   unified-cost-consent-surface — Unified SPR-07 cost + consent surface
#   unified-flywheel-conformance — Unified SPR-08 flywheel + conformance gate
#   agent-gates          — SPR-03/04/08 unit gates (fast; CI-friendly)
#   deep-research        — ANT-DRL P-52..P-58 hermetic harness (SPR-DRL-02, SPR-DRL-08, SPR-DRL-09)
#   html-transport       — ANT-AHT P-59 ResearchArtifact transport gates
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

TSX="${ROOT}/apps/reading/node_modules/.bin/tsx"

require_tsx() {
  if [[ ! -x "${TSX}" ]]; then
    echo "FAIL: missing local tsx — run pnpm --dir apps/reading install" >&2
    exit 2
  fi
}

usage() {
  echo "Usage: canonical_verify.sh {profile|cascade|read-foundation|read-library|read-reader|read-curate|read-ad-border|read-voice-notes|read-rabbit-hole|read-passage-research|read-ad-escrow|write-outline-block|write-edit-capture|write-block-repository|write-structured-editor|write-brainstorm-interview|write-draft-generation-style|write-trace-to-source|write-pre-outline-freeform|write-style-conditioning|speak-consent-rights-gate|speak-async-voice-interview|speak-project-invitations|speak-compounding-interviewer|speak-cross-interviewee-verification|speak-contributor-economics|speak-economics-matrix|speak-biography-authoring|speak-publishing-physical|drw-reading-surface-transfer|unified-substrate-contract-lock|unified-remote-exec-fanout|unified-seams-and-collisions|unified-navigation-ia-taxonomy|unified-coordination-gate-ledger|unified-thread-navigation|unified-cost-consent-surface|unified-flywheel-conformance|handoff <md>|agent-gates|deep-research|html-transport}" >&2
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
  echo "== read-reader: activation dogfood closure guard =="
  "${PY}" -m pytest tests/test_read_activation_dogfood.py -q --tb=no
  echo "== read-reader: book reader surface =="
  (cd apps/reading && npm run test -- \
    src/modes/Reading/Reading.test.tsx \
    src/modes/Reading/ResearchThis.test.tsx \
    src/modes/Reading/TalkToBook.test.tsx \
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

cmd_write_draft_generation_style() {
  echo "== write-draft-generation-style: generation, citations, voice/style gate =="
  "${PY}" -m pytest \
    tests/test_draft_generation.py \
    tests/test_write_routes.py \
    tests/test_role_creative_writer.py \
    tests/test_contracts_write_lock.py \
    -q --tb=no
  echo "== write-draft-generation-style: client + outline/xray generation UI =="
  (cd apps/reading && npm run test -- \
    src/modes/Write/writeApi.test.ts \
    src/modes/Write/Outline.test.tsx \
    src/modes/Write/Xray.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: write-draft-generation-style"
}

cmd_write_trace_to_source() {
  echo "== write-trace-to-source: backend provenance + gated no-leak =="
  "${PY}" -m pytest \
    tests/test_trace_to_source.py \
    tests/test_write_routes.py \
    tests/test_contracts_write_lock.py \
    -q --tb=no
  echo "== write-trace-to-source: client masking + X-ray + one-reader route =="
  (cd apps/reading && npm run test -- \
    src/modes/Write/writeApi.test.ts \
    src/modes/Write/Xray.test.tsx \
    src/modes/Write/WriteHome.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: write-trace-to-source"
}

cmd_write_pre_outline_freeform() {
  echo "== write-pre-outline-freeform: context promotion + provenance =="
  "${PY}" -m pytest \
    tests/test_promote_context.py \
    tests/test_write_routes.py \
    tests/test_contracts_write_lock.py \
    -q --tb=no
  echo "== write-pre-outline-freeform: context window UI + no-fabrication gate =="
  (cd apps/reading && npm run test -- \
    src/modes/Write/ContextWindow/contextWindow.test.ts \
    src/modes/Write/ContextWindow/ContextWindow.test.tsx \
    src/modes/Write/writeApi.test.ts \
    src/modes/Write/WriteHome.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: write-pre-outline-freeform"
}

cmd_write_style_conditioning() {
  echo "== write-style-conditioning: prompt-level conditioning + no-training guard =="
  "${PY}" -m pytest \
    tests/test_style_conditioning.py \
    tests/test_draft_generation.py \
    tests/test_contracts_write_lock.py \
    -q --tb=no
  echo "CANONICAL_VERIFY_OK: write-style-conditioning"
}

cmd_speak_consent_rights_gate() {
  echo "== speak-consent-rights-gate: scoped consent + publish gate =="
  "${PY}" -m pytest \
    tests/test_speak_consent.py \
    tests/test_speak_publish.py \
    tests/test_seam_platform_authored_gate.py \
    tests/test_contracts_speak_lock.py \
    -q --tb=no
  echo "CANONICAL_VERIFY_OK: speak-consent-rights-gate"
}

cmd_speak_async_voice_interview() {
  echo "== speak-async-voice-interview: async voice-note interview + single voice owner =="
  "${PY}" -m pytest \
    tests/test_async_interview.py \
    tests/test_speak_invitee_voice.py \
    tests/test_acquisition_voice.py \
    tests/test_seam_voice_single_owner.py \
    tests/test_contracts_speak_lock.py \
    -q --tb=no
  echo "== speak-async-voice-interview: invitee voice UI =="
  (cd apps/reading && npm run test -- \
    src/modes/SpeakInvite/SpeakInvite.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: speak-async-voice-interview"
}

cmd_speak_project_invitations() {
  echo "== speak-project-invitations: project container + invite links =="
  "${PY}" -m pytest \
    tests/test_speak_project.py \
    tests/test_speak_api.py \
    tests/test_interview_project_listing.py \
    tests/test_contracts_speak_lock.py \
    -q --tb=no
  echo "== speak-project-invitations: Speak index UI =="
  (cd apps/reading && npm run test -- \
    src/modes/SpeakIndex/SpeakIndex.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: speak-project-invitations"
}

cmd_speak_compounding_interviewer() {
  echo "== speak-compounding-interviewer: context conditioning + no-training gate =="
  "${PY}" -m pytest \
    tests/test_compounding_interviewer.py \
    tests/test_speak_drw_gap_source.py \
    tests/test_speak_compounding_interviewer.py \
    tests/test_sprint16_interviews.py \
    tests/test_contracts_speak_lock.py \
    -q --tb=no
  echo "CANONICAL_VERIFY_OK: speak-compounding-interviewer"
}

cmd_speak_cross_interviewee_verification() {
  echo "== speak-cross-interviewee-verification: independent corroboration + honest surface =="
  "${PY}" -m pytest \
    tests/test_cross_interviewee.py \
    tests/properties/test_speak_properties.py \
    tests/test_speak_api.py \
    tests/test_contracts_speak_lock.py \
    -q --tb=no
  echo "== speak-cross-interviewee-verification: Speak agreement UI =="
  (cd apps/reading && npm run test -- \
    src/modes/Speak/Speak.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: speak-cross-interviewee-verification"
}

cmd_speak_contributor_economics() {
  echo "== speak-contributor-economics: payee mapping + escrow-only accrual =="
  "${PY}" -m pytest \
    tests/test_contributor_economics.py \
    tests/test_speak_api.py::test_release_payout_accrues_to_escrow_no_disbursement \
    tests/test_speak_api.py::test_release_payout_rejects_negative_budget \
    tests/test_contracts_speak_lock.py \
    -q --tb=no
  echo "== speak-contributor-economics: Speak settings owed-not-paid surface =="
  (cd apps/reading && npm run test -- \
    src/modes/Speak/Speak.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: speak-contributor-economics"
}

cmd_speak_economics_matrix() {
  echo "== speak-economics-matrix: four-cell policy + binding split =="
  "${PY}" -m pytest \
    tests/test_economics_matrix.py \
    tests/test_speak_api.py::test_full_operator_journey_to_public_publish \
    tests/test_speak_api.py::test_economics_surfaces_gate_status_gated_by_default \
    tests/test_speak_payout_verifier.py::test_economics_has_no_public_but_no_split_path \
    tests/test_contracts_speak_lock.py \
    -q --tb=no
  echo "== speak-economics-matrix: Speak settings four-cell matrix =="
  (cd apps/reading && npm run test -- \
    src/modes/Speak/SpeakSettings.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: speak-economics-matrix"
}

cmd_speak_biography_authoring() {
  echo "== speak-biography-authoring: outline, deepening, draft honesty =="
  "${PY}" -m pytest \
    tests/test_biography_authoring.py \
    tests/test_speak_write_composer.py \
    tests/test_speak_api.py::test_full_operator_journey_to_public_publish \
    tests/test_contracts_speak_lock.py \
    -q --tb=no
  echo "== speak-biography-authoring: Speak assembly UI + API mapping =="
  (cd apps/reading && npm run test -- \
    src/modes/Speak/Speak.test.tsx \
    src/lib/speakApi.biography.test.ts \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: speak-biography-authoring"
}

cmd_speak_publishing_physical() {
  echo "== speak-publishing-physical: publish gate + servability + physical quote =="
  "${PY}" -m pytest \
    tests/test_speak_publish.py \
    tests/test_seam_platform_authored_gate.py \
    tests/test_speak_api.py::test_full_operator_journey_to_public_publish \
    tests/test_contracts_speak_lock.py \
    -q --tb=no
  echo "== speak-publishing-physical: Speak publish/quote UI =="
  (cd apps/reading && npm run test -- \
    src/modes/Speak/Speak.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: speak-publishing-physical"
}

cmd_drw_reading_surface_transfer() {
  echo "== drw-reading-surface-transfer: DRW lock + reader contract =="
  "${PY}" -m pytest \
    tests/test_contracts_drw_lock.py \
    substrate/contracts/__tests__/test_reading_surface.py \
    tests/test_contracts_dependency_map.py \
    tests/test_coordination_no_fork.py \
    -q --tb=no
  echo "== drw-reading-surface-transfer: Roadmap UI fixture =="
  (cd apps/reading && npm run test -- \
    src/modes/Coordination/Roadmap.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: drw-reading-surface-transfer"
}

cmd_unified_substrate_contract_lock() {
  echo "== unified-substrate-contract-lock: contracts, DAG, locks, conformance =="
  "${PY}" -m pytest \
    tests/test_contracts_unified_lock.py \
    tests/test_contracts_dependency_map.py \
    tests/test_contracts_drw_lock.py \
    tests/test_contracts_conformance.py \
    tests/test_conformance_gate.py \
    -q --tb=no
  echo "== unified-substrate-contract-lock: standalone conformance gate =="
  "${PY}" tools/codegen/check_conformance.py
  echo "== unified-substrate-contract-lock: invariant registry meta-check =="
  "${PY}" -m pytest tests/test_invariant_registry_meta.py -q -p no:cacheprovider -p no:xdist --tb=no
  echo "CANONICAL_VERIFY_OK: unified-substrate-contract-lock"
}

cmd_unified_remote_exec_fanout() {
  echo "== unified-remote-exec-fanout: remote runner, isolation, budget, fallback =="
  "${PY}" -m pytest \
    tests/test_remote_exec_runner.py \
    tests/test_remote_exec_isolation.py \
    tests/test_remote_exec_budget.py \
    tests/test_remote_exec_fallback.py \
    tests/test_launch_n_spr05.py \
    tests/test_contracts_unified_lock.py \
    -q --tb=no
  echo "CANONICAL_VERIFY_OK: unified-remote-exec-fanout"
}

cmd_unified_seams_and_collisions() {
  echo "== unified-seams-and-collisions: seam contracts + collision guards =="
  "${PY}" -m pytest \
    tests/test_seam_conformance.py \
    tests/test_seam_no_copy.py \
    tests/test_seam_voice_single_owner.py \
    tests/test_seam_single_escrow_writer.py \
    tests/test_seam_platform_authored_gate.py \
    tests/test_integration_invariants.py \
    tests/e2e/test_flywheel.py \
    tests/test_contracts_unified_lock.py \
    -q --tb=no
  echo "CANONICAL_VERIFY_OK: unified-seams-and-collisions"
}

cmd_unified_navigation_ia_taxonomy() {
  echo "== unified-navigation-ia-taxonomy: workflow taxonomy + nav IA =="
  "${PY}" -m pytest tests/test_contracts_unified_lock.py -q --tb=no
  echo "== unified-navigation-ia-taxonomy: frontend taxonomy and four-door rail =="
  (cd apps/reading && npm run test -- \
    src/shell/taxonomy.test.ts \
    src/shell/navrail.panel.test.tsx \
    src/shell/workflowStub.test.tsx \
    src/shell/navrail.spr06.test.tsx \
    src/shell/navrail.hotkeys.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: unified-navigation-ia-taxonomy"
}

cmd_unified_coordination_gate_ledger() {
  echo "== unified-coordination-gate-ledger: no-fork ledger + roadmap =="
  "${PY}" -m pytest \
    tests/test_coordination_no_fork.py \
    tests/test_integration_invariants.py::test_invariant_5_no_fork_gate_ledger \
    tests/test_contracts_unified_lock.py \
    -q --tb=no
  echo "== unified-coordination-gate-ledger: Coordination UI =="
  (cd apps/reading && npm run test -- \
    src/modes/Coordination/Coordination.test.tsx \
    src/modes/Coordination/Roadmap.test.tsx \
    src/modes/OperatorDashboard/OperatorDashboard.test.tsx \
    src/modes/Sources/Sources.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: unified-coordination-gate-ledger"
}

cmd_unified_thread_navigation() {
  echo "== unified-thread-navigation: thread reconstruction + API =="
  "${PY}" -m pytest \
    tests/test_thread_reconstruct.py \
    tests/test_thread_no_duplicate.py \
    tests/test_thread_api.py \
    tests/test_integration_invariants.py::test_invariant_6_no_duplicate_thread \
    tests/test_contracts_unified_lock.py \
    -q --tb=no
  echo "== unified-thread-navigation: breadcrumb + jump UI =="
  (cd apps/reading && npm run test -- \
    src/shell/ThreadBreadcrumb.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: unified-thread-navigation"
}

cmd_unified_cost_consent_surface() {
  echo "== unified-cost-consent-surface: cost + consent no-disbursement =="
  "${PY}" -m pytest \
    tests/test_cost_consent_no_disbursement.py \
    tests/test_contracts_unified_lock.py \
    -q --tb=no
  echo "== unified-cost-consent-surface: Coordination cost/consent UI =="
  (cd apps/reading && npm run test -- \
    src/modes/Coordination/CostConsent.test.tsx \
    --reporter=dot)
  echo "CANONICAL_VERIFY_OK: unified-cost-consent-surface"
}

cmd_unified_flywheel_conformance() {
  echo "== unified-flywheel-conformance: flywheel + integration invariants =="
  "${PY}" -m pytest \
    tests/e2e/test_flywheel.py \
    tests/test_integration_invariants.py \
    tests/test_contracts_unified_lock.py \
    -q --tb=no
  echo "== unified-flywheel-conformance: conformance gate + negative controls =="
  "${PY}" -m pytest tests/test_conformance_gate.py -q --tb=no
  echo "== unified-flywheel-conformance: standalone conformance script =="
  "${PY}" tools/codegen/check_conformance.py
  echo "CANONICAL_VERIFY_OK: unified-flywheel-conformance"
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
  require_tsx
  "${TSX}" tools/agent/verify_handoff.ts "$f"
  echo "== handoff: session theater grep =="
  bash scripts/audit_agent_session.sh "$f"
  echo "CANONICAL_VERIFY_OK: handoff ($f)"
}

cmd_agent_gates() {
  echo "== agent-gates: vitest handoff linter =="
  (cd apps/reading && npm run test:handoff)
  echo "== agent-gates: settings activation boundary =="
  (cd apps/reading && npm run test -- src/modes/Settings/Settings.test.tsx --reporter=dot)
  echo "== agent-gates: Read activation CLI + closure guard =="
  "${PY}" -m pytest \
    tests/test_read_activation_dogfood.py \
    tests/test_antiek_read_activation_cli.py \
    -q --tb=no
  echo "== agent-gates: Read activation e2e evidence draft helper =="
  (cd apps/reading && npm run test:ams -- --run e2e/_ams/read_activation_evidence.test.ts --reporter=dot)
  echo "== agent-gates: pytest audit + canonical wrapper =="
  "${PY}" -m pytest \
    tests/test_audit_agent_session.py \
    tests/test_canonical_verify.py::test_canonical_verify_handoff_uses_repo_local_tsx \
    tests/test_canonical_verify.py::test_canonical_verify_agent_gates_hermetic \
    tests/test_canonical_verify.py::test_canonical_verify_usage_names_every_dispatch_subcommand \
    tests/test_canonical_verify.py::test_canonical_verify_dispatch_commands_emit_unique_success_markers \
    tests/test_platform_exec_matrix.py \
    tests/test_ci_informational_gates.py \
    tests/test_ci_pytest_timeout_docs.py \
    tests/test_auth_diagnostic_verification.py \
    tests/test_memory_mcp_verification_docs.py \
    tests/test_rlm_deferral_docs.py \
    tests/test_autoresearch_prime_deferral_docs.py \
    tests/test_loop3_unlock_docs.py \
    tests/test_phase2_audit_v5.py \
    tests/test_privacy_control_plane_docs.py \
    tests/test_read_decision_docs.py \
    -q --tb=no
  echo "CANONICAL_VERIFY_OK: agent-gates"
}

cmd_html_transport() {
  echo "== html-transport: P-59 ANT-AHT bundle =="
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
  echo "== deep-research: P-52 Loop 1 E2E =="
  "${PY}" -m pytest tests/test_loop_one_orchestrator.py::test_loop_one_happy_path_emits_completed -q --tb=no
  echo "== deep-research: P-53 invariant negative =="
  "${PY}" -m pytest tests/test_deep_research_complete.py::test_drw_only_trajectory_fails_without_synthesis -q --tb=no
  echo "== deep-research: P-54 session reconstruct =="
  "${PY}" -m pytest tests/test_cascade_session.py -q --tb=no
  echo "== deep-research: P-55 PromotionFunnel serialize =="
  "${PY}" -m pytest tests/test_research_runner.py::test_promotion_funnel_serialized_no_lock_timeout -q --tb=no
  echo "== deep-research: P-56 knowledge.reused (two-run) =="
  "${PY}" -m pytest tests/test_flywheel_reuse.py::test_two_run_contract_gather_emits_knowledge_reused_on_second_start -q --tb=no
  echo "== deep-research: P-57 Exa gather mock E2E =="
  "${PY}" -m pytest tests/test_exa_gather_loop.py -q --tb=short
  echo "== deep-research: P-58 parent-terminal observability =="
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
    read-rabbit-hole) cmd_read_rabbit_hole ;;
    read-passage-research) cmd_read_passage_research ;;
    read-ad-escrow) cmd_read_ad_escrow ;;
    write-outline-block) cmd_write_outline_block ;;
    write-edit-capture) cmd_write_edit_capture ;;
    write-block-repository) cmd_write_block_repository ;;
    write-structured-editor) cmd_write_structured_editor ;;
    write-brainstorm-interview) cmd_write_brainstorm_interview ;;
    write-draft-generation-style) cmd_write_draft_generation_style ;;
    write-trace-to-source) cmd_write_trace_to_source ;;
    write-pre-outline-freeform) cmd_write_pre_outline_freeform ;;
    write-style-conditioning) cmd_write_style_conditioning ;;
    speak-consent-rights-gate) cmd_speak_consent_rights_gate ;;
    speak-async-voice-interview) cmd_speak_async_voice_interview ;;
    speak-project-invitations) cmd_speak_project_invitations ;;
    speak-compounding-interviewer) cmd_speak_compounding_interviewer ;;
    speak-cross-interviewee-verification) cmd_speak_cross_interviewee_verification ;;
    speak-contributor-economics) cmd_speak_contributor_economics ;;
    speak-economics-matrix) cmd_speak_economics_matrix ;;
    speak-biography-authoring) cmd_speak_biography_authoring ;;
    speak-publishing-physical) cmd_speak_publishing_physical ;;
    drw-reading-surface-transfer) cmd_drw_reading_surface_transfer ;;
    unified-substrate-contract-lock) cmd_unified_substrate_contract_lock ;;
    unified-remote-exec-fanout) cmd_unified_remote_exec_fanout ;;
    unified-seams-and-collisions) cmd_unified_seams_and_collisions ;;
    unified-navigation-ia-taxonomy) cmd_unified_navigation_ia_taxonomy ;;
    unified-coordination-gate-ledger) cmd_unified_coordination_gate_ledger ;;
    unified-thread-navigation) cmd_unified_thread_navigation ;;
    unified-cost-consent-surface) cmd_unified_cost_consent_surface ;;
    unified-flywheel-conformance) cmd_unified_flywheel_conformance ;;
    handoff) cmd_handoff "$@" ;;
    agent-gates) cmd_agent_gates ;;
    deep-research) cmd_deep_research ;;
    html-transport) cmd_html_transport ;;
    *) usage ;;
  esac
}

main "$@"
