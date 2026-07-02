# Read-shell convergence + Read-surface dormancy — keep, don't amputate

**Decision date:** 2026-06-03
**Status:** ✅ Settled (SPR-04 of Antiek — Convergence)
**Owner:** operator + SPR-04
**Scope:** front-end only (`apps/reading/`). Backend, the §9 legal gate
(SPR-03), dispatch (SPR-05), and the reuse loop (SPR-06) are out of scope and
untouched.

SPR-04 was chartered to (1) converge two competing "Werner" reading shells
into one canonical #54 ice-fishing shell by stripping #52's competing edits,
and (2) for every dormant Read feature make a binary WIRE-or-KILL decision.
**Both premises turned out to be false against this branch's actual git
history and source — and that finding, not a fork-strip, is the substance of
this decision.** Trust the code, not the PR body (rigor #1).

## Finding 1 — there is NO Werner shell fork on this branch (nothing to strip)

The brief stated `PenguinMascot.tsx` was a "MIXED state" where #52's
cursor-pursuit logic partially overwrote #54's ice-fishing animation. The git
history disproves this:

- **#52 (`a6dabd0`, `prcrouch/ant-h2v`) touched ZERO files under
  `apps/reading/src/` and ZERO werner/penguin/icefishing files.** Its diff is
  purely the ANT-H2V cascade + agent-execution platform work: `.github/`,
  `CLAUDE.md`, `docs/agent-execution/*`, `docs/specs/ant-h2v/*`,
  `apps/reading/package.json`, `apps/reading/vitest.agent.config.ts`. Verified:
  `git show --name-only a6dabd0 | grep -iE 'werner|penguin|icefish'` → empty.
- **#52 is an ANCESTOR of #54.** `git merge-base 811c194 a6dabd0` → `a6dabd0`
  itself. #52 (PR merge) landed first; #54's werner-ice SPR-13–16 series
  (`f1893c5 → b580718 → … → 811c194`) was then built on top. They are not two
  competing forks of the same files — they are sequential, on disjoint file
  sets.
- **Every line of `PenguinMascot.tsx` is attributed (git blame) to the
  werner / SPR-05 / SPR-06 / SPR-12 / SPR-14–16 series** (`e52f63d`,
  `215fba8`, `b580718`, `10bb8cc`, `9365c31`, `dd8537b`, `ccb4c66`) — all
  #54-canonical ice-fishing work. No line is from #52's branch.
- The only commits in the entire history mentioning "cursor-pursuit /
  cursor-follow / pursuit" are the werner-ice commits themselves
  (`ccb4c66` "tighten cursor-follow lag from 5s to 0.5s" is an *enhancement to*
  the ice-fishing follow, not a competing implementation). There is no
  separate "cursor-pursuit PR that removed ice-fishing."

`PenguinMascot.tsx` is **already a coherent #54 ice-fishing component**: it
imports the canonical `../werner` subsystem, gates timings on
`wernerIceFishingCursor`, and hosts the SPR-15 reel-mode pursuit-toward-
centered-lagged-hook effect (`reelStep` / `isReelSettled` /
`centerLaggedTarget`, lines ~352–426). `AppShell.tsx` mounts both
`<PenguinMascot />` (line 156) and `<WernerIceCursorShell />` (line 159).

**Verification (before-state honesty crux):** the ice-fishing tests
(`PenguinMascot.iceFishing.test.tsx` + `.compat.` + `.integration.`) **pass
17/17**; the whole `src/shell/` suite passes 96/96 under the default config;
`npx tsc -b` exits 0; `npm run build` emits the production bundle (including
the werner ice-fishing image assets). A `werner-waddle` timing assertion in
the **pre-existing SPR-06 roam test** (`PenguinMascot.test.tsx:250`, NOT an
ice-fishing test) reproduces in **~2 of 3 full-file runs** of that file under
fake-timer load but **passes 5/5 when isolated** (`-t`) — i.e. test-pollution /
scheduling jitter, **not** an ice-fishing contradiction and **not** introduced
by SPR-04 (it predates this sprint in the werner series; SPR-04 changed zero TS).
It does not gate this diff; the flaky roam test is flagged for a separate fix.

**Action taken: NONE on the shell.** Stripping #52 lines from PenguinMascot
would have meant inventing edits that do not exist. The convergence was
already complete; SPR-04 verified it rather than fabricating a fork-strip.

### #52's cascade value, explicitly preserved (separate concern)

#52's ANT-H2V cascade + agent-execution-platform changes (the docs/ +
.github/ + package.json files above) are left **byte-for-byte untouched**.
They are a genuinely separate concern (research cascade decomposition + agent
execution gates) with nothing to do with the Werner reading shell, and SPR-04
neither resolves nor disturbs them.

### Fairness — steelman of #52's "cursor-pursuit" direction

A cursor-pursuit treatment (the mascot simply easing toward the cursor) would
be **simpler, lighter on animation, and arguably more accessible** than the
ice-fishing reel-pursuit + roam + emote machinery — fewer moving parts, less
to break under reduced-motion, no fishing-line geometry. The stakeholder who
would object to "make ice-fishing canonical" is the author of a cursor-pursuit
direction. The answer: the operator chose #54 (ice-fishing) as canonical, and
in this branch's history that choice was never actually contested in
`apps/reading/src` — #52 carries no competing Werner code to preserve, so there
is no collateral damage to that author's work. The ice-fishing component is
also coherent and well-tested (17 ice-fishing tests green), so #54 is not the
weaker implementation that rigor #2 says to flag before stripping.

## Finding 2 — Read-surface dormancy = ZERO (the "5 dormant modes" are a false positive for Read)

The capstone flagged 5 modes as dormant. **None of them is a Read feature.**
All canonical Read components are mounted and reachable:

| Read feature | mounted in | reachable? |
|---|---|---|
| `BookReader` (`modes/Reading`) | `App.tsx:161` route `/read/:documentId` | yes |
| `MetaReading` | `App.tsx:150,154` `/read/meta-reading[/:assetId]` | yes |
| `PersonalSpace` | `App.tsx:157,160` `/readings`, `/meta-readings` | yes |
| `ResearchThis` | `Reading/index.tsx` (BookReader) | yes |
| `VoiceNote` | `Reading/index.tsx` | yes |
| `TalkToBook` | `Reading/index.tsx` | yes |
| `TocPanel` | `Reading/index.tsx` | yes |
| `ReadingCompanion` | `Reading/index.tsx` | yes |
| `Attribution` | `Reading/index.tsx` | yes |

The 5 capstone-flagged modes are **§9.0-gated deferred monetization /
operator surfaces**, not Read features:

| Mode | file(s) | routed/mounted? | classification |
|---|---|---|---|
| `AdvertiserConsole` | `modes/AdvertiserConsole/` | no (0 importers outside self/stories/tests) | §9.0-gated, Wave-3 deferred |
| `CreatorPayouts` | `modes/CreatorPayouts/` | no (0 importers) | §9.0-gated, Wave-3 deferred |
| `Economics` (`AccrualView`) | `modes/Economics/` | no (0 `from .../modes/Economics` imports) | §9.0-gated, Wave-3 deferred |
| `MarketplaceMetrics` | `modes/MarketplaceMetrics/` | no (0 importers) | §9.0-gated, Wave-3 deferred |
| `PayoutDashboard` | `modes/PayoutDashboard/` | no (0 importers) | §9.0-gated, Wave-3 deferred |

(The 2 source references to "Economics" are doc-comments in
`apps/reading/src/reading-physics/types.ts:156` and
`augmentations/accrual.ts:5` — NOT imports of the `modes/Economics` mode,
which has zero real importers.)

### Decision: keep all 5 — defer, do NOT amputate

These modes are **intentionally unrouted** because the §9.0 legal gate (G2/G3
publisher opt-in + retrieval-time gating) is not closed: payouts, advertiser
onboarding, marketplace metrics, and accrual surfaces must not be reachable
until money-routing is legally activated. They are built-ahead surfaces
parked behind that gate, not orphaned half-features.

**Amputating them would be wrong, on two grounds:**

1. **It crosses the §9.0 legal gate (out of scope for SPR-04).** Deleting
   built monetization surfaces is a money-routing / legal-posture change the
   master-spec §9.0 reserves to the operator + counsel. SPR-04 is a
   front-end convergence; it has no authority to remove §9.0-gated surfaces.
2. **The brief's diligence-verified scope says so explicitly:** "deleting
   §9.0-gated built surfaces is wrong + crosses the legal gate." The
   sprint-page's original "amputate dormant Read features" milestone assumed
   real Read dormancy existed; it does not. The anti-purgatory principle
   targets *Read* features stuck unreachable — there are none.

**What would reverse this deferral:** the operator closing G2/G3 (§9.0
publisher opt-in + retrieval-time gating in prod) → at that point these 5
modes get routes + nav entries (a WIRE verdict), not deletion. Until then
they stay parked. The existing repo-wide reachability/anti-stranding gate
(`tools/lint/reachability_gate.py`, `docs/decisions/anti-stranding-gate.md`)
already grandfathers pre-existing zero-importer modules via its shrink-only
baseline, so these parked surfaces do not red that gate, and a *new* dead
Read module still would.

## Finding 3 — the Read reachability probe (SPR-01 contract, M5)

`tools/reachability/probes/read.py` registers with the SPR-01 probe runner
(discovered as `read`; `python -m tools.reachability.probe_runner --only
read`). It is **outcome-asserting, not file-presence**: it parses the SPA's
actual route table + shell mount + live variant and asserts —

1. `App.tsx` binds `<Route path="/read/:documentId" element={<BookReader …}>`
   (the route *resolves to the real reader*, not merely that a file exists);
2. `AppShell.tsx` **mounts** both `<WernerIceCursorShell />` and
   `<PenguinMascot />` in JSX (an imported-but-unmounted shell is the exact
   dormancy this gate kills);
3. `iceFishingFlags.ts` keeps `wernerIceFishingCursor` defaulting **ON**
   (ice-fishing is the live variant — #54 canonical, not a fork that disabled
   it).

**Teeth proven (rigor #3, momentary-removal → RED → restore → GREEN):**
removing the `/read/:documentId` route, unmounting `<WernerIceCursorShell />`,
or flipping the ice-fishing default each turns the probe RED (exit 1); all
three restored → GREEN (exit 0). The tree was fully restored afterward
(`git diff` over those three files is empty).

**Caveat (rigor #1, honest downgrade):** this is the SOURCE-ROUTE-TABLE form,
not a built-bundle headless render. A full-render probe would boot the emitted
`dist/` SPA in a headless browser, navigate to `/read/<id>`, and assert the
reading column + Attribution paint — catching a route present in source but
tree-shaken out of the bundle, or a render that throws at runtime. What would
unblock it: a Playwright/chromium harness in CI (`apps/reading` declares
`@playwright/test` + an `e2e` script; the chromium binary is not installed on
this box). Until then, the render-throw failure mode is covered by the jsdom
render suite `apps/reading/src/modes/Reading/Reading.test.tsx` (30 tests,
mounting `/read/:documentId` → BookReader and asserting Attribution + TocPanel
+ the float-menu render without a TypeError), which runs under `npm test`;
and tree-shaking of an unconditional top-level `<Route>` is not a real risk.
