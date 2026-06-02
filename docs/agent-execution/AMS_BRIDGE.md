# AMS bridge — ref-lint ↔ HARD_TO_VARY Phase E

**Status:** ANT-EXEC-H2V SPR-05 (2026-06-02)  
**Protocol:** `docs/agent-execution/HARD_TO_VARY.md`  
**AMS ledger:** `docs/ams-v2/verified-interfaces.md`  
**H2V tooling ledger:** `docs/htmlspec/antiek-hard-to-vary-execution/verified-interfaces.md`

This document wires the AMS-v2 **anti-fiction ref-lint** into agent-execution **Phase E — Bounded closure**, so UI/spec claims in sprint HTML and handoffs cannot pass closure while citing paths that never existed on `origin/main`.

---

## What runs where

| Layer | Path | Role |
|-------|------|------|
| Implementation | `tools/specs/verify_spec_refs.ts` | Extracts `.file` chips + inline repo paths from sprint HTML; `git cat-file -e origin/main:<path>`; exit **1** on bare absent chip paths |
| AMS entry | `tools/ams-v2/ref-lint.sh` | Stable shell entry cited by AMS and H2V docs (`npx tsx` → implementation) |
| Agent entry | `scripts/agent_ams_ref_lint.sh` | Executor-facing wrapper (repo root → `ref-lint.sh`) |
| Domain ledger | `docs/ams-v2/verified-interfaces.md` | Mountain-shell / Reading UI rows (AMS-v2 program) |
| Program ledger | `docs/htmlspec/antiek-hard-to-vary-execution/verified-interfaces.md` | ANT-EXEC gates + bridge rows (this sprint) |

**Canonical command (from repo root):**

```bash
bash scripts/agent_ams_ref_lint.sh docs/htmlspec/antiek-hard-to-vary-execution/sprint-05-ams-bridge.html
# equivalent:
bash tools/ams-v2/ref-lint.sh <sprint.html>
npx tsx tools/specs/verify_spec_refs.ts <sprint.html>
```

Record **command + exit + log path** in the handoff `### Gate results` table (Phase D/E).

---

## Phase E mapping

Phase E requires closure claims that **collapse** if evidence is removed (`HARD_TO_VARY.md` § Phase E).

| Phase E step | Ref-lint / ledger role | Forbidden pattern addressed |
|--------------|------------------------|----------------------------|
| **E1** — matrix / Scope Map rows filled | Every row that cites a **repo path** must resolve on `origin/main` or be prefixed `NEW:` in the sprint page the row came from | **F3** — “platform OK” backed by fictional UI paths (`#scene-root` fiction, `components/ProductsLauncher.tsx`, …) |
| **E2** — `### Not proved` before `### Status` | Ref-lint does not replace Not proved; it bounds **what was cited** so Not proved is honest | **F5** — invented DOM/API without ledger row |
| **E3** — handoff packet complete | When handoff or sprint HTML lists `.file` chips, run `agent_ams_ref_lint.sh` on those pages before `done` | **F4** — skipped diligence via deleted headings (complements `verify_handoff.ts`) |
| **E4** — steelman | Fast path: “spec paths are probably right.” Ref-lint falsifies in one command | AMS-v1 lineage (`HARD_TO_VARY.md` historical failures) |

**When to run (minimum):**

1. Before marking **done** on any sprint that adds or edits HTML under `docs/htmlspec/` or `docs/specs/` with `.file` dependency chips.
2. When a handoff **Files touched** or Scope Map cites a new `apps/reading/…` or `interfaces/…` path as load-bearing evidence.
3. After reconciling `docs/ams-v2/verified-interfaces.md` — re-lint the sprint page that cited changed rows.

**When ref-lint is N/A:** Session touched only Python cascade paths with no new spec HTML — say `N/A — no sprint HTML cited` in Gate results; do not substitute “I read the tree.”

---

## Verdict semantics (executor)

| Verdict | Meaning | Phase E impact |
|---------|---------|------------------|
| `PASS` | Path exists on `origin/main` | Row may be marked `tested` with file evidence |
| `NEW` | Cite used `NEW:` / `NEW-to-build:` prefix | Deliverable must land in same sprint or be in Not proved |
| `FAIL` | Bare `.file` chip absent on `origin/main` | **Block closure** — fix cite or add `NEW:` prefix |
| `ADVISORY-ABSENT` | Inline `<code>` prose path absent | Note in handoff; does not gate exit code |

Exit **0** = no chip-level fiction. Exit **1** = at least one `FAIL`. Exit **2** = usage error.

---

## Relationship to other ANT-EXEC gates

| Gate | Script | Phase | Complements ref-lint by… |
|------|--------|-------|---------------------------|
| Handoff schema | `npx tsx tools/agent/verify_handoff.ts` | D/E | Headings, Not proved order, pytest\|tail theater (F1) |
| Session theater | `bash scripts/audit_agent_session.sh` | D/E | F3 platform OK without Scope Map |
| AMS ref-lint | `bash scripts/agent_ams_ref_lint.sh` | **E** | F3/F5 path fiction in spec HTML |

Run handoff + audit + ref-lint when closing a spec-heavy sprint; cascade-only Python sprints may omit ref-lint with documented N/A.

---

## Example gate row (handoff paste)

```markdown
| AMS ref-lint | `bash scripts/agent_ams_ref_lint.sh docs/htmlspec/antiek-hard-to-vary-execution/sprint-05-ams-bridge.html` | 0 | (stdout) |
```

---

## Lineage

AMS-v1 shipped against interfaces that never resolved on `origin/main`. SPR-01 (AMS-v2) introduced `verify_spec_refs.ts` + `docs/ams-v2/verified-interfaces.md`. SPR-05 (ANT-EXEC-H2V) exposes the same gate on the agent-execution path so Phase E closure cannot bypass it.