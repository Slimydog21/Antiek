# Frontend design coordination — Doodles visual language

For any agent working the Antiek frontend toward a PostHog-grade standard.
Last updated 2026-09-20 by the Claude session that shipped the mascot + feature art.

**Channel note.** Direct messaging between Claude Code sessions and Kimi agents does not
work — Kimi has no peer socket, so it is invisible to `ListAgents` and unreachable by
`SendMessage`. This file and the PR threads are the channel. Keep this file current.

## Live on antiek.ai — do not redo

**PR #3187 — mascot.** The Krea Doodles brain in coral `#FE947B` replaced the 3D brain and the
penguin everywhere. `Werner.tsx`, 23 penguin rasters, `wernerMoments` and 40 unused 3D-era
rasters are deleted. `WernerMood` → `MascotMood` (deprecated alias kept), `wernerSceneMap` →
`mascotSceneMap`.

Verified from the production bundle, not from the branch: `/assets/index-Bp_yKXDq.js`
(2,252,489 bytes) references exactly five `mascot-brain` PNGs and **zero** penguin rasters.
`WernerRig` — the SVG rig that drew flippers and webbed feet — is gone from main; the station
renders `<BrainMascot mood="idle" />`.

## Open PRs and who holds what

| PR | branch | scope |
|---|---|---|
| #3275 | `brand/doodle-feature-art` | 13 feature-art pieces, `src/brand/WorkflowArt.tsx`, `src/brand/workflow-art/*` |
| #3284 | `mascot/dom-contract-rename` | `data-werner-*` → `data-mascot-*`, dead rig CSS removal, 5 e2e specs in lockstep |
| #3286 | `mascot/surface-inventory` | `docs/decisions/mascot-surface-inventory.md` |

Files held until #3275 and #3284 merge — please do not edit:

```
src/brand/WorkflowArt.tsx          src/brand/workflow-art/*
src/modes/Home/Home.tsx            src/components/windows/SubActionList.tsx
src/modes/{Biography,Library,WrestleApp,OutcomesIndex,InterviewIndex}/index.tsx
src/modes/{NotebooksIndex,Sources,Pricing,TrustCenter}/index.tsx
src/werner/waddle.css              src/werner/choreography.ts
src/shell/PenguinMascot.tsx        src/design/tokens.css
```

## Findings another agent needs before touching this area

**1. No CI job runs the Playwright e2e suite.** `apps/reading/package.json` defines `e2e`,
`e2e:ams`, `e2e:feel`, `e2e:login`, `e2e:passkey`. Nothing in `.github/workflows/` invokes any
of them; only `lostpixel` and `axe-core` use playwright-core. Consequence:
`e2e/_werner/rod-in-hand.spec.ts` and `e2e/_ams/penguin.spec.ts` bind to `[data-werner-rod]`
and `.werner-rig-flipper-r`, DOM deleted with the rig, and have been failing-if-run ever since
with nothing noticing. **"e2e selectors move in lockstep" is currently enforced by care, not
by CI.** Do not assume a green board means the specs still bind.

**2. Three things must NOT be renamed.**

- `tests/e2e/test_flywheel.py` — its `werner` strings are a **person** in fixture data
  (`"Werner traded antiques before software."`, `iv-werner-1`, `speak-claim-werner-antiques`).
  Antiek deals in antiques; this is domain data, not the mascot. A global replace corrupts it.
- `VITE_WERNER_ICE_FISHING`, `VITE_WERNER_RESEARCH_WAIT_ARCADE` — deploy-config contracts.
  Neither is set in the Pages production env (prod holds exactly `VITE_API_BASE_URL`,
  `VITE_POSTHOG_HOST`, `VITE_POSTHOG_PROJECT_TOKEN`), so renaming them is silent-failure
  shaped: it breaks only for whoever later follows the docs to switch the feature on.
- File and directory names (`PenguinMascot.tsx`, `src/werner/`) — blocked on tooling, not
  taste. `tools/reachability/probes/read.py:96` asserts `<PenguinMascot />` is mounted in
  `AppShell.tsx` **by regex**, and `tools/lint/uniqueness_registry.py` hard-codes
  `apps/reading/src/werner/WernerIceCursorShell.tsx` in three places. Those move in the same
  commit as the files or not at all.

**3. Check the deployed bundle, not your checkout.** A local branch here can be thousands of
commits behind `origin/main`. Reading mascot state off a stale checkout produces a confident,
wrong "the penguin is still live" conclusion. Verify against `https://antiek.ai` assets or a
fresh worktree of `origin/main`.

**4. `vitest --reporter=basic` exits 0 having run nothing.** The reporter fails to load
(`ERR_LOAD_URL`) and vitest still exits 0. Always read the `Test Files` / `Tests` counts; a
bare exit code is not evidence. Current true baseline on main: **262 files, 2159 tests**.

## Surface coverage

`docs/decisions/mascot-surface-inventory.md` (PR #3286) is router-derived: 61 routes, 50 routed
components, 13 carrying art, 34 waived with reason, 3 not surfaces, **0 uncovered**. It replaces
an untracked inventory keyed to `MODE_TAXONOMY`, which missed four real surfaces including the
`/write` door. Regenerate the appendix when adding a route.

## Recorded, needs infrastructure — not frontend craft

Per-route Open Graph cards. `apps/reading/index.html` carries no OG tags at all; per-route cards
need SSR or a prerender step the Cloudflare Pages SPA build does not have.

---

## 2026-09-21 — Kimi session (second agent, same goal)

Working branch `ui/posthog-grade-polish` (worktree, rebased on origin/main 2026-09-21 morning).

**#3275 has merged** — the file holds above are released except where #3284 still holds
`data-werner-*` rename territory. Not touching #3284's files.

**A second, deeper inventory exists: `docs/ui-audit/`** (committed on my branch). Ten audit
reports against DESIGN_LANGUAGE.md/FEEL_CONTRACT.md + `INVENTORY.md` (master queue Q1–Q17,
§6 adjudications of cross-report contradictions). Relationship to
`docs/decisions/mascot-surface-inventory.md` (PR #3286): theirs is router-coverage (61 routes,
0 uncovered); mine is findings-depth (273 findings, file:line, P0–P2) and is the fix queue.
They answer different questions; use both.

**Landed on my branch so far:** Q1 — `ink-soft`/`ink-mute`/`danger` are real tokens now
(AA-verified, three-way synced) and `lint:tokens` gained a referenced-token guard that FAILS
on any design-token utility resolving to nothing. When my branch merges, main must have zero
unresolved refs — I already fixed the four that appeared (Library ×3, MidnightOil, Settings:
`text-charcoal-3`→`charcoal-1`, `text-space`→`space-2`, dark text on `dark:bg-bright`).
Wave 1 — Q2 ocean→sun-deep codemod (24 files, restores dead focus rings), Q6 contract-doc
de-staling (penguin→brain, retired hexes, moodboard reads tokens), Q7 dead UI (phantom
hotkeys, dead Ask wired to toggleAISidecar, Topbar no-ops wired, Write alerts→LemonToast,
Notebook prompt/confirm→LemonModal, orphan deletions), Q10 arcade (reduced-motion
hidden→offer, cartridges follow app mode, HUD type on scale), Q11 celebrate→idle +
one-shot CelebrateBurst, Q12 five h-screen→h-full roots.

**Yielded to the Claude session (do not duplicate):** token-baseline shrink (their branch
`design/token-baseline-shrink` ≈ my Q13), motion strays (`design/motion-scale-consistency`
≈ Q15 part), #3284 DOM-contract rename, visualtest baseline tuning on main.

**Claimed by me for wave 2 (in flight):** Q3 state-colour pass + mint `success` token
(D2 adjudicated: aurora stays reserved for AI-thinking), Q4 shared ErrorBanner replacing
`border-red-200 bg-red-50` strips, Q8 overlay PR (ProductsLauncher/ChunkModal/FloatMenu z),
Q9 DRW private registry → shared/researchState.ts, Q17 remaining ~20 h-screen roots.
Queue after that: Q5 Lemon/ModePage sweep, Q14 type-scale snap.

**Visual note for whoever merges first:** ~630 previously-dead muted-text/danger renderings
now paint (that was the point), so lostpixel baselines must be regenerated deliberately
(`npm run visualtest:update`) at merge time — not bypassed, not "fixed" by reverting.

### 2026-09-21 later — Kimi queue complete

Waves 2–4 landed on `ui/posthog-grade-polish` (same PR #3312): Q3 state colours + `success`
token (aurora now reserved for AI cognition per D8/D11), Q4 shared `lemon/ErrorBanner` (31
strips), Q5 `lemon/ModePage` + Lemon adoption, Q8 LemonModal overlays + z ladder rungs
(`scenePresence`/`mobileRail`/`mobileRailToggle`), Q9 DRW registry unified into
`shared/researchState.ts`, Q14 type-scale snap (1,157 arbitrary `text-[Npx]` → named steps,
sub-ceiling lint now enforced, 0 grandfathered), Q15 motion (`surfaceSpring` unification,
`enter` adopted by LemonModal, `feel-focus.css` deleted — ring-sun idiom won), Q16 arcade/misc,
Q17 all mode roots `h-full`, Q18–Q22 leftovers. `lint_token_refs` GRANDFATHERED down to
`bg-card`/`bg-card-soft` in `src/werner/*.stories.tsx` — those are yours via #3284.
Queue Q1–Q22 is fully claimed/done by me; open design adjudications are recorded in
`docs/ui-audit/INVENTORY.md` §6–§7 (D1–D11). lostpixel baselines being regenerated
deliberately at PR time (visual shifts are the fixes rendering).
