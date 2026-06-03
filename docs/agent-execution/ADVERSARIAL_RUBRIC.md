# Adversarial handoff rubric

**Status:** Active — ANT-EXEC-H2V SPR-02 (2026-06-02)  
**Taxonomy:** `docs/agent-execution/THEATER_TAXONOMY.md` (T-01…T-14)  
**Protocol:** `docs/agent-execution/HARD_TO_VARY.md` (F1–F8)

Use this table on **every** agent handoff before merge. Mark each row **PASS** or **FAIL**. **Any FAIL ⇒ session fails adversarial re-read** unless remediated and re-audited.

**Grounding:** Rows cite egghead closure pattern, `DispatchDecomposer` contract case, AMS-v1 fiction ledger, `ccb4c66` Werner postmortem, and D17 deferral precision.

---

## Rubric (binary)

| ID | Check | PASS when | FAIL (theater) when | T-class | F# |
|----|-------|-----------|---------------------|---------|-----|
| R-01 | Env Card present | `### Env Card` with repo-root `pwd`, `.venv` python path, branch, SHA | Missing or "same as last time" | T-04, T-13 | F4 |
| R-02 | Interpreter sanity | `which .venv/bin/python` matches Env Card | System python or unstated interpreter | T-02 | F2 |
| R-03 | Verify log completeness | Full pytest/verify output retained (path or paste); not tail-only | Sole sign-off is `pytest \| tail` | T-01 | F1 |
| R-04 | Gate results table | Each gate: command + exit + log path (or `N/A — reason`) | "Tests passed" without commands | T-01, T-13 | F1 |
| R-05 | Scope Map bounded | Every claimed entry point has status + evidence file:line | "Platform OK" / "engine fine" without rows | T-03 | F3 |
| R-06 | Not proved before status | `### Not proved` lists non-claims **above** `### Status` | Superlatives with no not-proved section | T-03, T-13 | F3 |
| R-07 | Phase A contract lock | Signatures pasted OR `N/A — docs-only` with reason | API claims from memory (egghead pattern) | T-12 | — |
| R-08 | LLM on failure path | Explicit `LLM contacted: yes \| no` for bug sessions | Unstated for cascade/decompose bugs | T-09 | — |
| R-09 | Pre-network vs provider | TypeError before dispatch ⇒ not "provider down" | Blames model outage without repro | T-09 | F-equiv |
| R-10 | DispatchDecomposer proof | Production adapter test OR row `untested` | Only FakeDecomposer cited for adapter bug | T-10 | F-equiv |
| R-11 | Repro script cited | When sprint names `repro_cascade_decompose_contract.py`, exit code in handoff | Repro skipped; "already fixed" | T-12 | — |
| R-12 | Deferral cite precision | `engineering_deferrals.md:L###` @ SHA | Bare "D17" / "deferred" | T-08 | F8 |
| R-13 | D17 cluster honesty | Live-ingest deferral described as operator window, not missing code | "D17 blocks implementation" without L475+ text | T-08 | F8 |
| R-14 | AMS path fiction | Cited UI paths VERIFIED in ledger or prefixed `NEW:` | Bare fictional paths (AMS-v1 class) | T-11 | F3 |
| R-15 | spec_refs lint | Changed sprint HTML passes `verify_spec_refs.ts` when cited | Unlinted new paths in htmlspec | T-11 | F3 |
| R-16 | Invented performance | p95/fps/cost has artifact or explicit not-measured | "Feels snappy" / p95 without file (ccb4c66 class) | T-05, T-14 | F5 |
| R-17 | Werner lag claim | Measurement procedure or SPR-07 block documented | Hop-tuning closure without sample | T-14 | F5 |
| R-18 | xfail bite | xfail paired with bite fixture OR no xfail | Bare xfail as coverage | T-06 | F6 |
| R-19 | CI proof class | Serve/rights/craft cites blocking pytest/job name | Lost-Pixel/axe warn-only as legal proof | T-07 | F7 |
| R-20 | Template headings | All `TEMPLATES.md` `###` present or `N/A — reason` | Deleted/skipped headings | T-04 | F4 |
| R-21 | Steelman recorded | Handoff names fastest wrong path + what it loses | Only triumphant narrative | T-13 | — |
| R-22 | Commit/branch truth | Env Card SHA matches `git rev-parse HEAD` | SHA mismatch or fictional branch | T-02 | F2 |
| R-23 | Out-of-scope explicit | Temptations logged, not silently expanded | Drive-by refactors without map update | T-03 | F3 |
| R-24 | Anti-fiction NEW paths | `NEW:` prefix on paths absent from `origin/main` | Implied shipped path not on main | T-11 | F3 |
| R-25 | Theater class tagged | Auditor notes dominant T-## if remediated | Repeat FAIL with no T-class remediation | (index) | — |

---

## Quick verdict

| Outcome | Rule |
|---------|------|
| **PASS** | All R-01…R-24 PASS (R-25 is auditor notes) |
| **FAIL** | Any mandatory row FAIL |
| **CONDITIONAL** | Only R-16/R-17 FAIL with explicit `### Not proved` + merge blocker named — not theater if falsifiable |

---

## Worked FAIL examples (lineage)

| Session pattern | Rows that FAIL | Lesson |
|-----------------|----------------|--------|
| Egghead cascade close | R-03, R-05, maybe R-02 | Right diagnosis; verify/scope theater |
| "Provider down" on TypeError | R-09, R-08 | **DispatchDecomposer** pre-network |
| AMS-v1 sprint "green" | R-14, R-15, R-24 | Fiction paths |
| ccb4c66 hop "fixed lag" | R-16, R-17 | Measurement theater |
| "Deferred to D17" in handoff | R-12, R-13 | Ambiguous deferral |

---

## Mechanical gates (SPR-02)

```bash
rg -c '^### T-' docs/agent-execution/THEATER_TAXONOMY.md   # ≥ 12
rg -c '^\| R-' docs/agent-execution/ADVERSARIAL_RUBRIC.md # ≥ 20
```

---

## Related

| Sprint | Artifact |
|--------|----------|
| SPR-03 | `tools/agent/verify_handoff.ts` automates subset of R-01, R-03, R-04, R-20 |
| SPR-04 | `scripts/audit_agent_session.sh` grep for F1–F8 strings |
| SPR-06 | `CASE_STUDY_CASCADE.md` — full PASS example target |