# Frontend dependency patches, 2026-09-20

## Failure Dossier

After the Tiptap repair in PR #3260, npm audit still reported 23 affected package
entries: 2 critical, 9 high and 12 moderate. Runtime-only audit reported four
moderate entries. These counts are package entries, not distinct vulnerabilities
or proof of application exploitation.

### Numbered failure chain

1. PostHog's compatible transitive ranges retained DOMPurify 3.4.11 and fflate
   0.4.8, both with published advisories.
2. Router 6.30.4, PostCSS and several build dependencies retained older versions.
3. Lost Pixel 3.22.0 is its latest registry release but pins Axios 1.7.7,
   form-data 4.0.0 and serve-handler 6.1.6 exactly. Ordinary range updates cannot
   repair that chain. npm audit suggests a Lost Pixel downgrade to 3.0.5.
4. Explicit Lost Pixel overrides now select Axios 1.20.0, form-data 4.0.6 and
   serve-handler 6.1.7. The upload and static-serving API contracts are tested.

## Scope Map

This branch stacks on PR #3260 at 435985227c22d4c9d7268be4cc1c33794f7e1bcd.
It owns the two reading-app manifests, one local compatibility probe and this
record. The control-plane handoff preserves all unfinished PDF-removal obligations.
No PDF dependency, benchmark, renderer or visual baseline is removed.

### Entry points

Runtime changes: DOMPurify 3.4.15, nested fflate 0.4.9 and Router 6.30.6.
Development changes: PostCSS 8.5.28, browserslist 4.29.0 and its data packages,
brace-expansion 2.1.7/1.1.21, nanoid 3.3.19, undici 7.29.1 and the three
Lost Pixel overrides with their required dependencies. The final lock changes
26 records including root metadata. The Tiptap family remains at 3.31.3.

## Dependency patches — Handoff

### Env Card

Date UTC: 2026-09-20. Worktree:
/Users/slimydog/Antiek/.worktrees/frontend-dependency-patches-20260920.
Branch: fix/frontend-dependency-patches-20260920.
Base: 435985227c22d4c9d7268be4cc1c33794f7e1bcd.
Node 22.22.0 used for installation and verification. Registry/audit network used.
The compatibility probe uses synthetic values and loopback HTTP servers.
No application LLM, live visual service, production or paid calls were tested.

### Not proved

Remaining Vite high and Router moderate findings are not cleared. The other
moderate build-tool findings also remain. No remote Lost Pixel service or full
screenshot/baseline comparison ran. The static probe tests real serve-handler
with Lost Pixel's options, not its wrapper's port allocator. No production
version or application exploitability claim is made.

### Status

Local acceptance gates pass. Independent review and CI pending. Orchestrator
provisional readiness: 90/100; this is not independent acceptance or an overall
frontend-security score.

### Files touched

- apps/reading/package.json and package-lock.json
- apps/reading/scripts/verify_dependency_compat.mjs
- This diagnostic

### Milestones

- [x] Compatible patch resolution and scoped Lost Pixel overrides.
- [x] Clean install, full dependency-tree validation and renewed audit.
- [x] Full tests, types, production build, Storybook and upload/static probe.
- [ ] Independent review and CI.

### Gate results

Commands below run from apps/reading with Node 22 on PATH. Logs are under the
worktree's .audit directory.

| Gate | Result | Log |
|---|---|---|
| npm ci | exit 0 | patch-npm-ci.log |
| npm ls --all --json | exit 0 | patch-npm-ls.json |
| npm test | 2,159 tests, 262 files pass | patch-vitest.log |
| npm run build:check | types/build/budgets pass | patch-build.log |
| npm run build-storybook | pass | patch-storybook.log |
| node scripts/verify_dependency_compat.mjs | pass | committed-compat-probe.log |
| npm audit --json | exit 1, 10 moderate / 1 high / 0 critical | patch-full-audit.json |
| npm audit --omit=dev --json | exit 1, 2 moderate / 0 high / 0 critical | patch-runtime-audit.json |

Production bundle sizes are 635.03 KB gzip for index and 50.58 KB for lemon,
within 683.59 KB and 58.59 KB budgets. No assertions or baselines were weakened.

The committed probe calls Lost Pixel's real uploadShot and sendCheckCacheToAPI.
It verifies synthetic API headers, generated multipart boundary, field values,
filename, exact PNG bytes and JSON return. A 400 response raises an Axios error
without retry. Real serve-handler returns explicit HTML/PNG, HEAD and 404;
cleanUrls:false does not silently map /page to page.html. Servers close and the
temporary fixture directory is removed after the normal run.

### Decisions mid-flight

Overrides are scoped to Lost Pixel rather than changing every consumer. They
are necessary because the latest parent release has exact vulnerable pins.
Reconsider these overrides when Lost Pixel updates its own dependencies. Keep
this probe as the compatibility gate for subsequent updates.

### Assumptions surfaced

Package patches can alter rendering despite satisfying semver. The full suite,
production build and Storybook build passed; visual screenshot parity remains
unmeasured. Audit severity and availability are time-sensitive snapshots.

### Steelman rejected alternative

A blanket audit fix can downgrade Lost Pixel or jump Vite major versions without
proving their contracts. Scoped updates plus the actual upload API exercise
provide reviewable evidence while preserving those separate migration decisions.

### Open questions

The remaining runtime findings are in react-router and react-router-dom. Router
6.30.6 repairs one advisory but two others list 7.18.0 as the patched release.
The app uses BrowserRouter with client-side createRoot, outside the SSR advisory's
stated affected mode. Login still passes a query-derived next value to navigate;
its redirect behavior needs a separate source and browser investigation.
Vite 5.4.21 has the sole remaining high package finding; a major-version toolchain
upgrade requires its own compatibility proof. Lost Pixel retains moderate
esbuild findings, and Storybook/Vitest chains retain moderate findings.

### Next sprint can start when

The manifest owner coordinates the successor branch and records exact review
and gate evidence. Merge PR #3260 first, then rebase this stack without dropping
its dependency fixes. PDF removal remains an independent unfinished obligation.

### Out-of-scope temptations

Router 7 and Vite major upgrades, screenshot rebaselining, PDF deletion, production
changes and unrelated application refactors.
