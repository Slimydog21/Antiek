# ANT-H2V agent execution — verified interfaces (tooling ledger)

> **What this file is.** The anti-fiction ledger for the **agent-execution / HARD_TO_VARY**
> program (`docs/htmlspec/antiek-hard-to-vary-execution/`). It lists every load-bearing
> path ANT-EXEC sprints cite for gates and handoffs. UI surface truth for Mountain Shell
> remains in `docs/ams-v2/verified-interfaces.md` — do not duplicate those rows here;
> run ref-lint against both ledgers' sprint pages as needed.
>
> **Re-check a VERIFIED row:**
>
> ```sh
> git cat-file -e origin/main:scripts/agent_ams_ref_lint.sh && echo PRESENT
> ```
>
> **Re-check a sprint page:**
>
> ```sh
> bash scripts/agent_ams_ref_lint.sh docs/htmlspec/antiek-hard-to-vary-execution/sprint-05-ams-bridge.html
> ```

**Baseline:** `origin/main` @ merge tip when row was added; re-verify on dispute.  
**Bridge doc:** `docs/agent-execution/AMS_BRIDGE.md` (Phase E mapping).

---

## Legend

| Verdict | Meaning |
|---------|---------|
| `VERIFIED` | `git cat-file -e origin/main:<path>` exits 0 |
| `NEW-to-build` | Absent on baseline; cite only with `NEW:` in sprint HTML or ref-lint fails |

---

## 1. Protocol + templates (SPR-01)

| Concern | Path | Verdict | Notes |
|---------|------|---------|-------|
| Phase A–E protocol | `docs/agent-execution/HARD_TO_VARY.md` | `NEW-to-build` | Merge tip; flip to VERIFIED after `origin/main` contains path |
| Handoff paste | `docs/agent-execution/TEMPLATES.md` | `NEW-to-build` | Env Card, Scope Map, Gate results |
| Program index | `docs/htmlspec/antiek-hard-to-vary-execution/index.html` | `NEW-to-build` | Sprint roster + verify block |
| Theater taxonomy | `docs/agent-execution/THEATER_TAXONOMY.md` | `NEW-to-build` | SPR-02 T-01… |
| AMS bridge | `docs/agent-execution/AMS_BRIDGE.md` | `NEW-to-build` | SPR-05 — ref-lint ↔ Phase E |
| Cascade case study | `docs/agent-execution/cascade-case-study.md` | `NEW-to-build` | SPR-06 narrative |
| Werner adapter | `docs/agent-execution/WERNER_EXEC_ADAPTER.md` | `NEW-to-build` | SPR-07 — product htmlspec pointer |
| Canonical verify | `scripts/canonical_verify.sh` | `NEW-to-build` | SPR-08 profile/cascade/handoff/agent-gates |
| Platform matrix | `docs/agent-execution/PLATFORM_EXEC_MATRIX.md` | `NEW-to-build` | SPR-10 closure rows P-01…P-10 |

---

## 2. Handoff + session gates (SPR-03–04)

| Concern | Path | Verdict | Notes |
|---------|------|---------|-------|
| Handoff linter | `tools/agent/verify_handoff.ts` | `VERIFIED` | Schema: headings, Not proved order, F1 tail |
| Session theater grep | `scripts/audit_agent_session.sh` | `VERIFIED` | F1 pytest\|tail, F3 platform OK |
| Pass fixture | `tests/fixtures/agent_execution/handoff_pass.md` | `VERIFIED` | `AUDIT_OK` negative control pair |
| Fail fixtures | `tests/fixtures/agent_execution/handoff_fail_*.md` | `VERIFIED` | F1/F3 subprocess tests |

---

## 3. AMS ref-lint bridge (SPR-05)

| Concern | Path | Verdict | Notes |
|---------|------|---------|-------|
| Ref-lint implementation | `tools/specs/verify_spec_refs.ts` | `VERIFIED` | AMS-v2 SPR-01 M2; chip FAIL vs advisory inline |
| Ref-lint unit tests | `tools/specs/verify_spec_refs.test.ts` | `VERIFIED` | Fiction fixture → non-zero exit |
| AMS shell entry | `NEW: tools/ams-v2/ref-lint.sh` | `NEW-to-build` | SPR-05 — delegates to `verify_spec_refs.ts` |
| Agent wrapper | `NEW: scripts/agent_ams_ref_lint.sh` | `NEW-to-build` | SPR-05 — executor entry from repo root |
| Wrapper tests | `NEW: tests/test_agent_ams_ref_lint.py` | `NEW-to-build` | SPR-05 — subprocess pass/fail |
| AMS domain ledger | `docs/ams-v2/verified-interfaces.md` | `VERIFIED` | Reading UI / harness rows |
| H2V tooling ledger | `NEW: docs/htmlspec/antiek-hard-to-vary-execution/verified-interfaces.md` | `NEW-to-build` | This file |

**Sprint page under lint for this sprint:**

| Deliverable | Path | Verdict |
|-------------|------|---------|
| SPR-05 spec | `NEW: docs/htmlspec/antiek-hard-to-vary-execution/sprint-05-ams-bridge.html` | `NEW-to-build` |

---

## 4. Confirmed-absent paths (do not cite bare)

These are recorded so sprint HTML and handoffs fail ref-lint if reintroduced (AMS-v1 lineage). Real replacements live in `docs/ams-v2/verified-interfaces.md`.

| Fictional path | Real replacement |
|----------------|------------------|
| `apps/reading/src/scene/index.ts` | `apps/reading/src/scene/Scene.tsx` |
| `apps/reading/src/components/ProductsLauncher.tsx` | `apps/reading/src/shell/ProductsLauncher.tsx` |
| `apps/reading/src/components/FloatingSurface.tsx` | (none — use `components/windows/`) |

---

## 5. Phase E closure checklist (mechanical)

Before `### Status: done` on a spec-touching sprint:

1. `bash scripts/agent_ams_ref_lint.sh <sprint.html>` → exit **0**
2. `npx tsx tools/agent/verify_handoff.ts <handoff.md>` → `HANDOFF_OK`
3. `bash scripts/audit_agent_session.sh <handoff.md>` → `AUDIT_OK`
4. `### Not proved` lists what ref-lint + pytest did **not** cover
5. `./scripts/canonical_verify.sh agent-gates` → `CANONICAL_VERIFY_OK: agent-gates` (SPR-08/09)

---

## 6. CI (SPR-09)

| Concern | Path | Verdict | Notes |
|---------|------|---------|-------|
| Agent execution workflow | `.github/workflows/agent_execution_gates.yml` | `NEW-to-build` | path-filtered; cascade + handoff fixtures |

---

_Updated ANT-EXEC-H2V SPR-05–10 · 2026-06-02._