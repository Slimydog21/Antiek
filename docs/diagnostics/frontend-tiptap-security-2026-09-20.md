# Frontend Tiptap security repair, 2026-09-20

## Failure Dossier

The installed runtime @tiptap/core3.27.2 has two published advisories:
[Markdown parser CPU exhaustion](https://github.com/ueberdosis/tiptap/security/advisories/GHSA-j95f-988m-3j2f)
and [attribute prototype injection](https://github.com/advisories/GHSA-cp6q-959q-f8rh).
The npm audit snapshot rates the first high; the publisher page rates it moderate.
This discrepancy is retained rather than silently treating severity as universal.
The upstream patch floors are3.30.5 and3.30.4 respectively. Application exploit
reachability has not been established. No production incident is claimed.

### Numbered failure chain

1. Four direct Tiptap ranges allowed3.27.1; the lock selected3.27.2 throughout.
2. The runtime dependency audit reported1high and30moderate affected package entries.
3. Updating only direct packages failed npm exact peer constraints against old lock nodes.
4. Removing only the stale Tiptap lock records and resolving normally selected3.31.3
   throughout. No force or legacy-peer-deps bypass was used.
5. New @tiptap/pm requires prosemirror-model^1.25.11 and view^1.42.3,
   so the lock also advances those to1.25.11 and1.42.4.

## Scope Map

Only apps/reading/package.json, package-lock.json and this dossier are owned.
Four manifest minimums advance to^3.30.5. Existing PDF runtime, benchmark,
lucide-react, p5 and other unrelated dependencies are preserved.

### Entry points

Notebook hydration/autosave and Write editor transactions are the affected
application contracts. npm audit verifies dependency advisories, not exploitation.
Build/typecheck and the existing editor/full Vitest suites verify compatibility.
No application source or test logic changes are included.

## Tiptap dependency repair — Handoff

### Env Card

Date UTC:2026-09-20. Worktree:
/Users/slimydog/Antiek/.worktrees/frontend-tiptap-security-20260920.
Branch:fix/frontend-tiptap-security-20260920.
Base:f24981db2bde8ce2fb88158fc54460cfd168c294.
Local Node25.6.1; alternate Node22.22.0. CI currently selects Node20.
Registry/audit network used. No application LLM or production calls.

### Not proved

Application exploitability, deployed dependency versions, runtime moderate findings,
development high/critical findings and PDF-removal completion remain open.
Browser interaction has not been rerun for this dependency-only change.

### Status

In progress. Final local gates pass; independent acceptance and CI pending.
Orchestrator readiness estimate:90/100, provisional until independent review
and CI. This does not grade overall frontend security or deployed behavior.

### Files touched

apps/reading/package.json; apps/reading/package-lock.json; this dossier.

### Milestones (checkboxes)

- [x] Ownership handoff and package-family resolution.
- [x] Audit removes all Tiptap findings and runtime high finding.
- [x] Final clean install, full tests, types, production build and bundle budgets.
- [ ] Independent acceptance and CI.

### Gate results

Evidence lives in this worktree's private .audit directory.
Initial clean npm ci passes; npm ls Tiptap peers passes.
Initial build:check passes, index636.55KB gzip below683.59KB and lemon50.60KB
below58.59KB. Node25 Vitest reports44failures/2115passes due localStorage
API errors; the Node22 rerun passes2159tests across262files. Logs: tiptap-npm-ci.log, tiptap-npm-ls.json,
tiptap-build.log, tiptap-vitest.log, tiptap-vitest-node22.log.
After restoring25unrelated Vitest optional esbuild records, final Node22
npm ci and npm ls pass. Final full suite again passes2159tests/262files.
Final build:check passes including tsc, index635.11KB and lemon50.58KB gzip
within the same budgets. Logs: tiptap-final-npm-ci.log, tiptap-final-npm-ls.json,
tiptap-final-vitest.log, tiptap-final-build.log. The final lock changes32records:
root,29Tiptap packages and2requiredProseMirror packages; no unrelated records.

A local package-level probe compares actual installed old/new core modules.
An own __proto__ input produced an inherited onerror marker on3.27.2;3.31.3
produces none and preserves the ordinary title. The probe passes. Small inline
parser timings are retained as observations, not a calibrated performance gate.
Evidence: .audit/tiptap-security-probe.mjs and .audit/tiptap-security-probe.json.

Audit exits1 because other findings remain. Runtime:4moderate,0high,0critical.
Full:12moderate,9high,2critical,23affected package entries. Counts are not
independent advisories. Logs: tiptap-runtime-audit.json, tiptap-full-audit.json.

### Decisions mid-flight

The blocked PDF-removal owner transferred manifest editing only. PR734 is closed
unmerged atb5aca057144e886c56bde85fb1869976812ca604. Its ancestry appears in
main through e34710fbe, but its PDF removal is absent from main's contents.
Independent content audit scored confidence99/100. The PDF lane must coordinate
manifest ownership return, rebase deletion, migrate remaining callers and prove
stale-panel fallback/importer/build/bundle behavior. Historical lockfiles must
not overwrite newer dependencies. The handoff is in .infinite/agent-board.json.

### Assumptions surfaced

A patched family may introduce editor regressions despite valid npm peers;
existing real-engine tests and production build are required.

### Steelman rejected alternative

A broad npm audit fix could reduce more findings in one command. It also proposes
an unrelated Lost Pixel downgrade and Vite major changes. Those require separate
compatibility work and are not evidence for this runtime repair.

### Open questions

Remaining runtime packages:dompurify,fflate,react-router,react-router-dom.
Lost Pixel/form-data/axios and other development findings need their own repair.

### Next sprint can start when

This manifest lane records exact commit, independent acceptance and compatibility
results so subsequent dependency or PDF work can build on a known state.

### Out-of-scope temptations

PDF runtime deletion, Vite upgrades, production deployment, changes to test
assertions and broad application-source refactors.
