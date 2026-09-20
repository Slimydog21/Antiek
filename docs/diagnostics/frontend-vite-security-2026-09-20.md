# Vite security and development-entry repair, 2026-09-20

## Failure Dossier

After PR #3263, Vite 5.4.21 was the only high-severity package entry in the
reading-app audit. The three Vite advisories affect versions through 6.4.2.
Vite 6.4.3 is patched and satisfies the installed React plugin 4.7.0 and
Storybook builder 8.6.18 peer ranges. It also supports the existing Node 20 CI
and locally tested Node 22 runtime. A Vite 8 migration is not required to clear
these particular advisories.

### Numbered failure chain

1. Upgrade only Vite to ^6.4.3 and its nested esbuild/platform packages.
2. Clean installation, full frontend tests, production and Storybook builds pass.
3. A real development-server probe passes HTTP/HMR/proxy checks but stalls in
   client-environment shutdown. Its dependency scanner reports an unresolved
   import from generated storybook-static/assets, not the application source.
4. Vite's default scanner uses **/*.html, excluding dist but not storybook-static.
   This incorrectly treats generated Storybook and diagnostic HTML as app entries.
5. optimizeDeps.entries now names index.html, which imports src/main.tsx.
   Normal dependency discovery through application imports remains enabled.
6. The strengthened probe serves an actual optimized dependency, waits for
   requests to settle and reports PASS only after normal server shutdown.

The first probe cleared its watchdog too early during cleanup. Its earlier
printed PASS was not a terminal successful run. That process was explicitly
terminated, and a diagnostic run timed out with exit 1. Both logs are retained.
The final probe keeps its watchdog through cleanup and exits 0 normally.

## Scope Map

Stacked on PR #3263 at c94596cfc. Only package manifests, vite.config.ts, the
new verification script and this record change. The manifest adds verify:deps
for the predecessor's committed Lost Pixel probe and verify:vite-dev for this
probe. No visual baseline, application source, Router or PDF change is included.
The lock changes 29 records: root, Vite, its esbuild and platform packages.

### Entry points

The [Vite 6 migration guide](https://v6.vite.dev/guide/migration.html) informed
checks for changed configuration defaults and tool compatibility. This app does
not customize resolve.conditions, use library build mode or Sass configuration.
The installed Storybook builder overrides optimizeDeps.entries with its story
entries, so the application entry restriction does not replace Storybook's scan.
Storybook is rebuilt to test that contract, rather than relying only on source.

## Vite upgrade — Handoff

### Env Card

Date UTC: 2026-09-20. Branch: fix/frontend-vite-security-20260920.
Worktree: /Users/slimydog/Antiek/.worktrees/frontend-vite-security-20260920.
Base: c94596cfc. Node 22.22.0. Registry/audit network used. Development probe
uses synthetic loopback HTTP and WebSocket services, with env-file loading off.
No application LLM, production, paid provider or remote visual service tested.

### Not proved

Windows-specific alternate-path exploits cannot be reproduced on this Mac.
The probe verifies configured HTTP proxies, not the /ws backend proxy.
No rendered browser interaction or screenshot parity check ran for this upgrade.
Remaining moderate dependencies and Router migration remain open.

### Status

Final local tests/builds pass after the entry correction. Independent review
and CI remain pending. Provisional readiness 90/100 until those gates complete. This does not establish deployed security or full product completion.

### Files touched

- apps/reading/package.json and package-lock.json
- apps/reading/vite.config.ts
- apps/reading/scripts/verify_vite_dev.mjs
- This diagnostic

### Milestones

- [x] Patched Vite family with valid peers and clean installation.
- [x] Reproduce generated-HTML scanner error and repair its entry contract.
- [x] Real optimized dependency, HMR, HTTP proxy and file-deny verification.
- [x] Final tests/builds after the entry correction.
- [ ] Independent review and CI.

### Gate results

Commands run from apps/reading under Node 22. Evidence is in worktree .audit.

| Gate | Result | Log |
|---|---|---|
| npm ci | exit 0 | vite-npm-ci.log |
| npm ls --all --json | no problems, exit 0 | vite-npm-ls.json |
| npm audit --json | exit 1: 10 moderate, zero high/critical; no Vite entry | vite-audit.json |
| Final npm test | 2,159 tests / 262 files pass | vite-final-vitest.log |
| Final build:check | types/build/budgets pass | vite-final-build.log |
| Final build-storybook | pass | vite-final-storybook.log |
| Cwd-corrected pre-fix dev probe | exit 1 on cleanup deadline; scanner error | vite-dev-cwd-baseline.log |
| npm run verify:vite-dev after entry fix | normal exit 0, including optimized dependency and cleanup | vite-dev-final.log |
| npm run verify:deps | pass on upgraded Vite tree | vite-lostpixel-compat.log |

Final bundle sizes are 635.37 KB gzip for index and 51.03 KB for lemon, within
683.59 KB and 58.59 KB limits.

The development probe tests SPA /login, main TSX transformation, HMR client and
WebSocket custom-message delivery, every configured HTTP proxy against a local
responder, and file deny with a served public control and denied synthetic .env.
Its deadline includes cleanup. It does not force a successful exit or disable
dependency optimization to evade the failure.

### Decisions mid-flight

Choose Vite 6 because it clears the observed advisories and fits existing peers.
Restrict scanning to the real app entry rather than adding an unrelated package
solely to satisfy generated Storybook output. Read-only reviewer confidence was
97/100 for the scanner diagnosis, 85/100 for the precise shutdown mechanism;
the exact stranded promise was not identified, so that causality remains bounded.

### Assumptions surfaced

A valid peer graph is necessary but insufficient. Full tests, production build,
Storybook and an actual server are required to establish local compatibility.

### Steelman rejected alternative

Jumping to Vite 8 follows npm audit's generic suggestion, but would exceed the
installed Storybook peer range. Vite 6.4.3 clears the listed advisories while
preserving the current build-tool contracts.

### Open questions

Ten moderate package entries remain across Router, Lost Pixel/esbuild,
Storybook and Vitest. The separate login policy lane repairs a reproduced
malformed-destination failure; it does not substitute for Router's dependency
migration or claim all its advisory paths are fixed.

### Next sprint can start when

Coordinate the manifest successor with this owner. Merge the dependency stack
in order: PR #3260, then #3263, then this branch, with checks on integrated state.

### Out-of-scope temptations

Router migration, PDF runtime deletion, screenshot rebaselining and production
changes remain separate work.
