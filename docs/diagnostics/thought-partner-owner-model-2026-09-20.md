# Thought-partner owner-selected models

Sidecar and Brainstorm now send an explicit account model choice to `/thought-partner`. Selected turns use the existing owner-scoped reserve/send/settle gateway, return the actual route receipt, and fail without falling back to a shared provider. The default route retains its existing request and response shape.

## Contract and scope

`parse_owner_turn_selection(request, model_choice, operation_id)` requires a valid choice and bounded operation ID together, then derives the authenticated owner. `dispatch_owner_turn(app, selection, prompt, investigation_id)` binds the assembled prompt hash to the operation authority and delegates to `dispatch_talk_to_book_byot`. The handler validates selection before retrieval and runs selected dispatch in a worker thread.

Before this change, both UI entry points and the endpoint used only house dispatch. No paid LLM was contacted to reproduce that gap.

| Entry point | Status | Evidence | Live provider |
|---|---|---|---|
| Selected POST `/thought-partner` | tested | `tests/test_thought_partner_owner_byot.py` | no, recording adapter |
| Default POST `/thought-partner` | tested | explicit legacy response-shape test in the same module | no |
| Sidecar selector, receipt, uncertain outcome | tested | `AISidecar.modelChoice.test.tsx`, browser journey | no, synthetic HTTP fixtures |
| Brainstorm selector, receipt, unavailable route | tested | `ThoughtPartnerPanel.modelChoice.test.tsx`, browser journey | no, synthetic HTTP fixtures |

## Handoff

### Env Card

| Field | Value |
|---|---|
| Date UTC | 2026-09-20 |
| Repo root | `/Users/slimydog/Antiek/.worktrees/thought-partner-owner-model-20260920` |
| Branch | `feat/thought-partner-owner-model-20260920` |
| Base SHA | `f24981db2bde8ce2fb88158fc54460cfd168c294` |
| Python | `.venv/bin/python`, symlink to canonical platform environment |
| Python version | 3.12.13 |
| Frontend | Node 22, existing matching-manifest node_modules symlink |
| LLM contacted this session | yes for independent GLM and MiMo code reviews; no live product inference |
| Network required for gates | React Doctor package resolution; contract tests use local synthetic data |

### Not proved

- Production deployment, paid provider health, and real account onboarding were not exercised.
- The isolated browser page mounts the real components with synthetic HTTP responses. It proves interaction and request wiring, not full-shell layout or production authentication.
- Settings namespace migration, removal of live shared keys, shared credential variants, and Write model selection remain separate work.
- The full backend suite is not green. The existing policy-tag test fails identically at the base and on this branch.

### Status

`in_progress`: implementation and bounded local verification complete; draft review and CI remain before integration.

### Files touched

- `interfaces/research/api/app.py`: thought-partner DTOs and handler only.
- `interfaces/research/api/thought_partner_byot.py`: selected-turn validation, owner gateway, receipt.
- `tests/test_thought_partner_owner_byot.py`: 17 route-visible cases using real encrypted credentials, signed sessions, and usage settlement with a recording provider adapter.
- `apps/reading/src/api/thoughtPartner.ts`: semantic launch identity, receipt parsing and safe failure messages.
- `AISidecar.tsx` and `ThoughtPartnerPanel.tsx`: model picker and receipt integration, with adjacent model-choice tests.
- `ThoughtPartnerFocusTray.tsx`: extraction of existing focus-tray behavior to keep the panel readable and avoid an introduced React Doctor finding.
- This handoff.

### Milestones (checkboxes)

- [x] Selected turns enforce owner authority and exactly-once spend, including concurrent duplicates.
- [x] Both UI paths snapshot model choice before asynchronous context composition.
- [x] Scoped tests, build, review, and synthetic browser checks complete.
- [ ] CI and integration.

### Gate results

All local log paths below are relative to the repo root. Scratch logs and browser fixtures are intentionally not product files.

| Gate | Command | Exit/result | Log path |
|---|---|---|---|
| Coupled owner routes | `.venv/bin/python -m pytest tests/test_thought_partner_owner_byot.py tests/test_talk_to_book_owner_byot.py tests/test_start_research_owner_dispatch.py tests/byot -q` | 0, 94 passed | `.audit/owner-coupled-final.log` |
| Base comparison | `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m pytest tests/test_thought_partner_owner_byot.py tests/test_thought_partner.py tests/test_thought_partner_account_memory.py -q --timeout=30 --junitxml=.audit/base.xml` | 1, 14 failed / 19 passed on base with initial 13 new cases | `/tmp/antiek-thought-partner-base-20260920/.audit/base.log` |
| Matching branch comparison | Same selection and environment, output `.audit/branch.xml` | 1, 1 failed / 32 passed; 13 resolved, zero introduced | `.audit/branch.log`, `.audit/failure-set-comparison.json` |
| Ruff | `.venv/bin/python -m ruff check interfaces/research/api/app.py interfaces/research/api/thought_partner_byot.py tests/test_thought_partner_owner_byot.py` | 0 | `.audit/backend-ruff.log` |
| Helper types | `.venv/bin/python -m mypy --follow-imports=silent interfaces/research/api/thought_partner_byot.py` | 0 | `.audit/thought-partner-mypy.log` |
| App types | scoped mypy including `app.py` | 1, four unchanged base diagnostics for xhtml2pdf/ebooklib imports | `.audit/backend-mypy-full.log`; base `.audit/base-mypy.log` in baseline worktree |
| UI regressions | From `apps/reading`: `npx vitest run src/components/AISidecar.modelChoice.test.tsx src/modes/BrainstormStation/ThoughtPartnerPanel.modelChoice.test.tsx src/components/ai/ModelUsagePicker.test.tsx` | 0, 3 files / 13 tests | `.audit/frontend-vitest-final.log` |
| Types and build | From `apps/reading`: `npm run build` | 0, existing large-chunk warnings | `.audit/frontend-build-final.log` |
| React Doctor | From `apps/reading`: `npx --yes react-doctor@latest --verbose --scope changed` | 0, all 6 intended TS files scanned, no introduced issues, score 81 unchanged | `.audit/frontend-reactdoctor-final.log` |
| GLM backend review | Read-only review of backend implementation and tests | ACCEPT, reviewed 15 cases; final two add legacy-shape and concurrent-duplicate coverage | `.audit/backend-glm-review.log` |
| MiMo frontend review | Read-only review of final frontend implementation and tests | ACCEPT, no blockers | `.audit/frontend-mimo-review.log` |
| Browser interaction | `browser-harness`, isolated Chromium at local Vite page | Both selections sent expected choice + separate operation IDs, both receipts visible; uncertain outcome showed safe warning; 3 deliberate requests, no automatic retry, no JS errors | `.audit/browser-final.json`, `.audit/browser-unknown.json`, `.audit/browser-final.png` |

The baseline comparison predates four added cases. The final 94-test run includes all 17 new cases. The remaining identical failure is `tests.test_thought_partner::test_thought_partner_policy_tag_threads_the_section_9_gate`. An earlier concurrent test log is invalid and excluded from evidence.

### Decisions mid-flight

The backend hashes the complete assembled prompt into resource authority because budget estimation alone binds length rather than content. Reusing an operation ID with changed history, context, prompt, or investigation cannot replay an unrelated answer or spend again.

The UI retains a selected unavailable model and displays a useful error. An uncertain provider response prompts the user to inspect usage. Neither case silently retries or switches to house dispatch.

### Assumptions surfaced

This work inherits the established owner gateway and its settings namespace. It does not make sentinel-owned legacy model registrations account-owned. PR #3197 addresses that separate migration boundary.

### Steelman rejected alternative

Adding a picker without changing dispatch would provide a small UI patch, but the selected credential would not control inference or spending. Reusing the existing owner gateway makes the selection enforceable and retains its durable settlement behavior.

### Open questions

- Integrate account namespace migration before relying on legacy model registrations in multi-user onboarding.
- Complete shared credential variants and Write selection in their own bounded changes.
- Follow up the pre-existing policy-tag failure without weakening retrieval policy in this change.

### Next sprint can start when

The draft is available for review. Live-account verification requires the account namespace migration and an explicitly chosen provider budget.

### Out-of-scope temptations

No unrelated retrieval policy, global bootstrap, credentials, schema, or deployment changes.
