# Platform execution matrix (ANT-EXEC-H2V SPR-10)

**Status:** Active closure matrix — every platform-wide claim must cite a row here or an equivalent handoff `### Scope Map`.

**Protocol:** `docs/agent-execution/HARD_TO_VARY.md` Phase B/E · **Gates:** `scripts/canonical_verify.sh`

| ID | Surface | Entry point | Hermetic gate (command) | Operator gate | Default `### Not proved` |
|----|---------|-------------|-------------------------|---------------|--------------------------|
| P-01 | Cascade auto-decompose | `POST /research/plans` omit `sub_questions` | `./scripts/canonical_verify.sh cascade` | `docs/agent-execution/OPERATOR_VERIFY_CASCADE_DECOMPOSE.md` | Live LLM decompose on operator keys |
| P-02 | DispatchDecomposer adapter | `roles/cascade_planner/planner.py` | `pytest tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response -q` | same as P-01 | Event-bus decomposer parity |
| P-03 | Cascade HTTP light route | `tests/test_cascade_create_plan_light.py` | included in `canonical_verify.sh cascade` | — | Full `test_cascade_api.py` collection |
| P-04 | Decomposer call sites | `scripts/audit_decomposer_call_sites.sh` | included in `canonical_verify.sh cascade` | — | Runtime-only branches |
| P-05 | Cascade edit contract | `PlanTree` edits + `/research/plans/{root_id}/edit` | included in `canonical_verify.sh cascade` | — | Full launch/session journey |
| P-06 | Parallel cascade orchestration | `CascadeSession` + `/research/sessions/{id}` | included in `canonical_verify.sh cascade` | — | Long-running live provider behavior |
| P-07 | Structural gap detection | `substrate/gap_detection/` + Speak `DRWGapSource` | included in `canonical_verify.sh cascade` | — | Live model phraser / recall tuning |
| P-08 | Universal ingest | `substrate/research_bridge/ingest_file.py` | included in `canonical_verify.sh cascade` | — | OCR/live large-file extraction |
| P-09 | Glass-box monitor UI | `apps/reading/src/modes/DeepResearchWorkspace/` | included in `canonical_verify.sh cascade` | — | Browser/device visual QA |
| P-10 | Read servable-corpus gate | `substrate/books/` + `interfaces/research/api/books.py` | `./scripts/canonical_verify.sh read-foundation` | — | Counsel/legal policy beyond encoded gate |
| P-11 | Read library browse | `/library` + `apps/reading/src/modes/Library/` | `./scripts/canonical_verify.sh read-library` | — | Browser/device visual QA |
| P-12 | Read book reader | `/read/:documentId` + `apps/reading/src/modes/Reading/` | `./scripts/canonical_verify.sh read-reader` | — | Browser/device visual QA |
| P-13 | Read prompt-to-curate | `substrate/books/curate.py` + `/books/curate` | `./scripts/canonical_verify.sh read-curate` | — | Web discovery before ingest |
| P-14 | Read ad-border inventory | `substrate/ad_inventory/` + reader ad rails/impressions | `./scripts/canonical_verify.sh read-ad-border` | — | Browser/device visual QA |
| P-15 | Read voice notes | `interfaces/research/api/read_voice.py` + reader voice-note UI | `./scripts/canonical_verify.sh read-voice-notes` | — | Live Whisper/provider-key behavior |
| P-16 | Read conversational rabbit hole | `AISidecar` voice replies + `TalkToBook` book Q&A | `./scripts/canonical_verify.sh read-rabbit-hole` | — | Live provider latency / browser-device audio QA |
| P-17 | Read passage research | `substrate/books/passage_research.py` + `ResearchThis` handoff | `./scripts/canonical_verify.sh read-passage-research` | — | Live Research provider / browser navigation QA |
| P-18 | Read ad-revenue escrow | `substrate/marketplace_metrics/book_escrow.py` + reader impression flush | `./scripts/canonical_verify.sh read-ad-escrow` | — | Live advertiser inventory / Stripe disbursement |
| P-19 | Write outline-block model | `substrate/write/outline_block.py` + `/write/blocks` routes | `./scripts/canonical_verify.sh write-outline-block` | — | Browser/device visual QA |
| P-20 | Write edit-trajectory capture | `substrate/edit/` + Write editor edit payload mapping | `./scripts/canonical_verify.sh write-edit-capture` | — | Browser/device live typing QA |
| P-21 | Write block repository | `substrate/write/folders.py` + `substrate/write/block_search.py` + repository UI | `./scripts/canonical_verify.sh write-block-repository` | — | Browser/device drag-and-drop QA |
| P-22 | Write structured block editor | `apps/reading/src/modes/Write/Editor/` + generated draft mount | `./scripts/canonical_verify.sh write-structured-editor` | — | Browser/device live editing QA |
| P-23 | Write brainstorm interview | `substrate/write/brainstorm_blocks.py` + `IdeaDump` section emission | `./scripts/canonical_verify.sh write-brainstorm-interview` | — | Live interviewer/ASR provider QA |
| P-24 | Write draft generation style | `substrate/write/draft_generation.py` + `creative_writer` route/UI | `./scripts/canonical_verify.sh write-draft-generation-style` | — | Live provider/output-quality QA |
| P-25 | Write trace to source | `substrate/write/trace.py` + Write editor/X-ray open path | `./scripts/canonical_verify.sh write-trace-to-source` | — | Browser/device reader navigation QA |
| P-26 | Write pre-outline freeform | `substrate/write/promote_context.py` + `ContextWindow` | `./scripts/canonical_verify.sh write-pre-outline-freeform` | — | Browser/device drag/drop + live generation QA |
| P-27 | Write style conditioning | `substrate/write/style_profile.py` + `creative_writer.style_guide` conditioning | `./scripts/canonical_verify.sh write-style-conditioning` | — | Live author-exemplar quality QA |
| P-28 | Speak consent rights gate | `substrate/speak/consent.py` + `publish_gate.py` + subject/takedown gates | `./scripts/canonical_verify.sh speak-consent-rights-gate` | — | Counsel/jurisdiction legal review |
| P-29 | Speak async voice interview | `substrate/speak/async_interview.py` + invitee voice route/UI | `./scripts/canonical_verify.sh speak-async-voice-interview` | — | Real-device microphone/ASR provider QA |
| P-30 | Speak project invitations | `substrate/speak/project.py` + `invitations.py` + Speak index | `./scripts/canonical_verify.sh speak-project-invitations` | — | Real invite delivery/email/domain QA |
| P-31 | Speak compounding interviewer | `substrate/speak/interviewer_context.py` + DRW gap source + interviewer role | `./scripts/canonical_verify.sh speak-compounding-interviewer` | — | Live interviewer output-quality QA |
| P-32 | Speak cross-interviewee verification | `substrate/speak/corroboration.py` + Speak agreement surface | `./scripts/canonical_verify.sh speak-cross-interviewee-verification` | — | Human judgment on nuanced contradictions |
| P-33 | Agent handoff schema | `tools/agent/verify_handoff.ts` | `./scripts/canonical_verify.sh handoff <md>` | — | Narrative quality / intent |
| P-34 | Session theater grep | `scripts/audit_agent_session.sh` | paired with handoff subcommand | — | Claims outside markdown packet |
| P-35 | AMS spec ref-lint | `scripts/agent_ams_ref_lint.sh` | `bash scripts/agent_ams_ref_lint.sh <sprint.html>` | — | Playwright mountain shell |
| P-36 | Reading substrate pytest | `.github/workflows/ci.yml` `pytest` job | CI on `main` (full suite) | — | Local hardware parity |
| P-37 | Werner mascot / hop | `apps/reading` Werner paths per Werner htmlspec | `canonical_verify.sh agent-gates` + case study §5 | Werner operator card (htmlspec) | Measured p95 / fps without artifact |
| P-38 | Serve / rights / legal | production deploy surfaces | **No** informational CI job alone (F7) | operator deploy checklist | Jurisdiction-specific legal review |

## How to use

1. **Phase B:** Copy relevant rows into handoff `### Scope Map` with `tested: yes|no` and log path.
2. **Phase D:** Run hermetic column; paste exit codes into `### Gate results`.
3. **Phase E:** Anything still in “Default Not proved” must appear under handoff `### Not proved` before `### Status`.

## Anti-fiction

- Do not add a row without a falsifiable command or named CI job.
- “Platform OK” without row IDs is **F3** (`THEATER_TAXONOMY.md` T-03).
