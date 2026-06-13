# Parity audit — 2026-06-13 (ALC SPR-09 M5 — FINAL PARITY AUDIT / capstone done-bar)
Rubric version: PostHog SHA 9c06e96956f68b6cd67e39e30df8ff736e1fcaad
Antiek tree: working tree @ 2026-06-13 — `caffen/ALC-integration` @ `3263cc5d` (ALL 8 sprints merged)
Auditor context: INDEPENDENT capstone run. Graded the INTEGRATED surface fresh BEFORE reading the four per-sprint audits (audit-spr05/06/07/08). Adversarial posture: default-to-refuted, hunting for a dimension that regressed when the sprints combined or a grade an individual audit inflated.

Honest scope (verbatim from the brief): NO live Krea token in this environment, so the FALLBACK / procedural experience is graded — which the rubric grades as FIRST-CLASS, not a degradation. The live-art crossfade is ONE element; scene beauty, motion, Werner character, shell crispness, and the evidence layer are all gradeable now. Where a grade depends on observing LIVE art (e.g. the crossfade in motion) it is flagged as awaiting operator activation (SPR-09 M2/M3) and the observable surface is graded.

All `file:line` re-resolved on the live integrated tree. Every count records its command/path.

---

## ADDENDUM — POST-REMEDIATION RE-AUDIT (2026-06-14, product-character fix)

The 2026-06-13 capstone below found the all-four gate MISSED on ONE dimension — **product character 1/3** — because the reading-mode floor tripped the rubric's level-1 absence anchor ("exactly 1 named story for a component with ≥2 meaningful states") on `ResearchThis.stories.tsx` (1 story / ≥3 states) and `VoiceNote.stories.tsx` (1 story / ≥6 states). A scoped, **additive** remediation then authored named, co-located Storybook stories for the four reading-mode stateful surfaces. This addendum re-grades that one dimension on the remediated tree and re-confirms the other three. The body of the 2026-06-13 audit below is preserved verbatim as the pre-remediation record; where it says "Product character 1 — MISSES," read the corrected grade in this addendum.

### What changed (verified additive — `git diff HEAD` + `git status`)
- **Modified:** `apps/reading/src/modes/Reading/ResearchThis.stories.tsx` (1→4 named stories: `Idle`/`Spinning`/`NotFound`/`Failed`); `apps/reading/src/modes/Reading/VoiceNote.stories.tsx` (1→7: `Capture`/`Transcribing`/`Correcting`/`TranscriptionUnavailable`/`Saving`/`Saved`/`SaveFailed`).
- **New:** `apps/reading/src/modes/Reading/PersonalSpace/PersonalSpace.stories.tsx` (4: `Loading`/`Empty`/`Populated`/`Error`); `apps/reading/src/modes/Reading/MetaReading/MetaReading.stories.tsx` (4: `Idle`/`ReopenLoading`/`ReopenError`/`SavedReport`); `apps/reading/src/modes/Reading/storyFetch.tsx` (a Storybook-only `window.fetch` + mic/recorder stub, restored-on-unmount).
- **NO runtime/prod source touched.** The full change set is exactly `*.stories.tsx` + `storyFetch.tsx` (+ this audit doc). The other three dimensions rest on runtime CSS/components/motion/focus/evidence rails and are mechanically unaffected.

### Stories reach the REAL state (not hollow renders) — verified
- `apiFetch` (`apps/reading/src/lib/api.ts:60-66`) is a thin wrapper over the global `fetch`; `stubFetch` swaps `window.fetch`, so `spinResearch`/`transcribeAudio`/`saveVoiceNote`/`listPersonalSpace`/`getSavedMetaReading` all route through the stub into the component's REAL reducer.
- VoiceNote: `stubRecorder`'s `FakeRecorder` matches `useVoiceRecorder`'s real surface (`getUserMedia` + `MediaRecorder.start/stop/ondataavailable/onstop/mimeType`), driving the genuine `recording → stopped → transcribing → correcting → saving/saved` path.
- MetaReading re-open stories use `parameters:{router:false}` — an opt-out the preview decorator genuinely honors (`apps/reading/.storybook/preview.tsx:59`) — and supply `:assetId` via their own `MemoryRouter`, so the component's real `useParams` re-open effect (`MetaReading/index.tsx:58-92`) fires.
- `build-storybook` (`npx storybook build`) SUCCEEDS; all **23** reading-mode story entries (ResearchThis/VoiceNote/PersonalSpace/MetaReading) appear in `storybook-static/index.json` — **no "Unable to index"**. `npx tsc -b` exit 0; `npx vitest run src/modes/Reading` = 11 files / 98 tests passed (2026-06-14).

### Product-character RE-GRADE: 1 → **2\*** (was the MISS; now MEETS the gate)
- **The L1 absence anchor no longer fires on ANY in-scope reading-mode component.** All 7 story-bearing reading components carry ≥2 named stories: AdBorder 4, HouseSlot 2, TocPanel 2, ResearchThis 4, VoiceNote 7, PersonalSpace 4, MetaReading 4. Zero have exactly one story. The specific surfaces the prior audit cited (ResearchThis, VoiceNote) now author every meaningful state — idle/in-flight/known-error/transient-error; capture/transcribing/correcting/unavailable/saving/saved/save-failed — as distinct named stories that drive the real code path.
- **HONEST CAP at 2, not 3 — co-location is 58%, below the L3 ≥85% bar.** 7 of 12 in-scope reading-mode components carry a co-located story. Still un-storied (stateful): `index.tsx` (the Reading shell, 20 state signals), `TalkToBook.tsx` (8), `ArxivFrame.tsx` (6); plus low-state `Attribution.tsx`, `ReadingCompanion.tsx`. The rubric's L3 requires named-state authorship **AND** ≥85% co-location; the remediation cleared the first prong decisively but not the second. That is exactly the rubric's **L2**: "≥2 named stories per stateful component with ≥1 non-default state named, BUT … co-location below the ~85% bar." Reading-mode = **2**, an honest level, not an inflated 3.
- **Dimension roll-up (lowest in-scope surface — same rule as the body):** Scene 2, Shell 2, Werner 3\*, Reading-mode **2** (was 1), Fallback 3 → floor **2\***. The `*` is the named, justified cap: co-location < 85% (TalkToBook/ArxivFrame/Reading-shell still un-storied) — a future-sprint co-location lift, the same shape as Scene/Shell already at 2.
- **Gate clause:** 2-with-named-justified-exception = **≥ target**; AND 2 **> baseline 1** (a genuine LIFT, no longer a non-lift); AND nothing regressed. **All three clauses now hold.** This is the corrected reading of the body's "Product character — FAIL."

### Other three dimensions — re-confirmed unaffected (additive change)
- **Visual crispness 2\*** (Werner-mascot named exception) — runtime CSS/focus untouched; held.
- **Motion & life 3** — no keyframe/motion source touched; held (strongest dimension).
- **Evidence-backed craft 2\*** (RAIL-A single-theme/non-blocking/flagship-excluded; Lost-Pixel re-mint operator-deferred) — `build-storybook` still green (the story-evidence substrate is, if anything, broader: +4 indexed reading-mode state stories); RAIL-A/RAIL-B caps unchanged; held.

### CORRECTED DELTA TABLE (baseline-2026-06-12 → post-remediation)
| Dimension | Baseline 2026-06-12 | 2026-06-13 (pre-fix) | Post-remediation | Gate? |
|---|---|---|---|---|
| Visual crispness | 1 | 2\* | **2\*** | MEETS (2 + named Werner exc.) |
| Motion & life | 3 (A)/2 (B) | 3 | **3** | MEETS (target) |
| Product character | **1** | **1 (MISS)** | **2\*** | **MEETS (2 + named co-loc<85% exc.; +1 > baseline)** |
| Evidence-backed craft | 2 | 2\* | **2\*** | MEETS (2 + named RAIL-A exc.) |

### CORRECTED HEADLINE VERDICT — ALL FOUR DIMENSIONS MEET THE GATE
Every dimension is now ≥ target (3, or 2 with a single named justified exception), every dimension is ≥ its 2026-06-12 baseline (product character LIFTED 1→2; the others held at or above baseline), and nothing regressed. **The SPR-09 capstone all-four-dimensions gate is MET.**

Named justified exceptions carried honestly (unchanged from the body): (1) Werner daypart-standing-art gap (`POSE_GAPS`); (2) reading-mode co-location < 85% — TalkToBook/ArxivFrame/Reading-shell still un-storied (a future co-location lift, not a faked state); (3) evidence-craft RAIL-A single-theme + non-blocking-in-CI + flagship-excluded, Lost-Pixel re-mint operator-deferred; (4) live-art-active confirmation awaits operator (SPR-09 M2/M3) — the procedural/fallback floor is the graded first-class state.

---


## HEADLINE VERDICT

**THREE of four dimensions meet the gate on the integrated surface; ONE MISSES.**

- Visual crispness: **1 → 2** — MEETS gate (2 with the named Werner-mascot exception; floor rose because the shell is no longer the floor).
- Motion & life: **3 → 3** — MEETS gate (held; the strongest dimension, no regression from combining sprints).
- **Product character: 1 → 1 — MISSES gate.** Reading-mode is still 1/3: `ResearchThis.stories.tsx` and `VoiceNote.stories.tsx` each ship exactly ONE named Storybook story for components with ≥3 and ≥6 meaningful states — the rubric's verbatim level-1 "default-looking surface" absence anchor. The dimension does NOT beat its 2026-06-12 baseline (1) and does NOT reach target (3, or 2-with-named-exception). Per the capstone rule ("the capstone does not ship a missed bar with an asterisk"), this is stated plainly: **SPR-09's all-four-dimensions gate FAILS on product character; the owning sprint is SPR-07.**
- Evidence-backed craft: **2 → 2** — MEETS gate (2 with named exceptions: RAIL-A single-theme/non-blocking/flagship-excluded; RAIL B depth shallow).

**No dimension regressed below its 2026-06-12 baseline.** The miss is a NON-LIFT (product character stayed at its baseline floor), not a regression introduced by combining sprints.

---

## Graded table (integrated surface @ 3263cc5d)
| Dimension | Scene | Shell | Werner | Reading-mode | Fallback | Dimension grade |
|---|---|---|---|---|---|---|
| Visual crispness | 3 | **3** | 2* | 2 | 3 | **2*** |
| Motion & life | 3 | 3 | 3 | 3 | 3 | **3** |
| Product character | 2 | 2 | 3* | **1** | 3 | **1** |
| Evidence-backed craft | 2* | 2 | 2 | 2 | 3 | **2*** |

**Roll-up rule:** *lowest in-scope surface* (same rule the baseline + every per-sprint audit used; the AUDITOR no-regression gate is per-surface, so an honest dimension roll-up reports the floor, not the average). A cell written `n*` is an `n` whose floor is a named, justified exception (named in findings). A dimension graded `n*` rolls up to `n` via the gate clause's "n with a single named justified exception."

---

## DELTA TABLE: baseline-2026-06-12 → final (integrated)
| Sub-dimension | Baseline 2026-06-12 | Final 2026-06-13 (integrated) | Δ | Owning sprint | Gate? |
|---|---|---|---|---|---|
| Visual crispness — Scene | 3 | 3 | — | SPR-05 | held |
| Visual crispness — Shell | **1** | **3** | **+2** | SPR-08 | LIFTED |
| Visual crispness — DIMENSION | **1** | **2*** | **+1** | SPR-08 | MEETS (2 + named exc.) |
| Motion & life — DIMENSION | 3 (Run-A) / 2 (Run-B) | **3** | — / +1 | SPR-06 | MEETS |
| Product character — Werner | 2 | **3*** | +1 | SPR-07 | lifted |
| Product character — Reading-mode | **1** | **1** | **0** | SPR-07 | **MISSES (no lift)** |
| Product character — DIMENSION | **1** | **1** | **0** | SPR-07 | **MISSES gate** |
| Evidence-craft — DIMENSION | 2 | **2*** | — | SPR-09 | MEETS (2 + named exc.) |

(Baseline motion was 3 on Run-A and 2 on Run-B per `baseline-stability-check.md`; the integrated grade lands at 3 — at-or-above both baseline runs.)

---

## Gate-clause verdict (per tools/parity/AUDITOR.md DOWNSTREAM GATE LANGUAGE)

> **Parity gate.** … **SPR-09** must reach target on **all four dimensions vs the 2026-06-12 baseline**. "**≥ target**" means **grade 3**, OR **grade 2 with a single named, justified exception recorded in the audit**. **No dimension may regress below its 2026-06-12 baseline grade** on any sprint.

Applied to the integrated surface, per dimension:

1. **Visual crispness — PASS.** Dimension grade 2 (floor: Werner 2 + reading-mode 2). Werner-2 is a NAMED, JUSTIFIED exception (a mascot, not a control — it carries token-sourced colour but exposes no interactive `:focus-visible` control of its own, so it cannot reach the level-3 state-pair-border bar; see findings). 2-with-named-exception = ≥ target. AND 2 > baseline 1. AND nothing regressed. **Meets all three clauses.**
2. **Motion & life — PASS.** Dimension grade 3 = target. 3 ≥ baseline (3 on Run-A, 2 on Run-B). Nothing regressed. **Meets all three.**
3. **Product character — FAIL.** Dimension grade 1 (floor: reading-mode 1). 1 is NOT target (not 3; not 2-with-named-exception — a single-happy-path-story for a ≥2-state component is the level-1 absence anchor, which is not an exception that can be "named and justified" — it is the failure the dimension exists to forbid). AND 1 is NOT > baseline 1 (it equals it — no lift). The "> baseline" and "≥ target" clauses BOTH fail. (The no-regression clause holds — it did not drop below 1.) **Fails 2 of 3 clauses. The gate is MISSED.**
4. **Evidence-backed craft — PASS.** Dimension grade 2 with named exceptions (RAIL-A rigor: single-theme, non-blocking-in-CI, flagship-excluded; RAIL B depth shallow). 2-with-named-exception = ≥ target. AND 2 ≥ baseline 2 (held; the gate requires "no regression below baseline," not a lift, for a dimension SPR-09 does not own as its single elevation target — but SPR-09's gate is "all four vs baseline," and held-at-baseline-2 with the exception named satisfies ≥ target). Nothing regressed. **Meets the clauses.**

**SPR-09 capstone gate: NOT MET.** Three dimensions clear; product character does not. Per the brief's rule, this is reported without an asterisk-ship: the all-four-dimensions bar is missed, and the owning sprint (SPR-07, product character) is the loop target.

---

## Per-dimension findings (integrated, with countable evidence)

### Visual crispness — 2*/3 (floor: Werner 2 + reading-mode 2; named Werner exception)
The headline integrated LIFT. Baseline floor was **Shell 1** ("a shared `.feel-focusable` focus bundle is defined and globally imported yet has ZERO className consumers"). On the integrated tree that floor is GONE — verified by count AND by a passing test.

- **Shell: 3/3 (was 1)** — `feel-focusable` now has real consumers across the shell: `grep -rln 'feel-focusable' apps/reading/src --include='*.tsx' | grep -v test` = **6 files** (NavRail, ProductsLauncher, ProjectTree, SceneChrome, ThreadBreadcrumb, WorkspaceWindow). EVERY control-bearing shell component carries designed keyboard focus: NavRail `apps/reading/src/shell/NavRail.tsx:211,293,483`, ProductsLauncher `:236` (the baseline's named embarrassment — the search input's bare `focus:border-sun` is now `feel-focusable … focus-visible:border-sun` at `apps/reading/src/shell/ProductsLauncher.tsx:236`), ProjectTree `:216,246,288,312`, SceneChrome `:202,232`, ThreadBreadcrumb `:123`, PenguinMascot `:788` (`focus-visible:outline-sun`). The three shell `.tsx` with zero focus rules — GlassSurface, ThreadJump, WorkflowStub — carry NO interactive controls (`grep -E '<button|onClick=|<input' = 0` on each), so they are not coverage gaps. The ring was upgraded to DUAL-TONE (sun core + ink halo) for legibility over BOTH light and dark surfaces and over the always-on scene: `apps/reading/src/design/feel-focus.css:43-50` (`outline:2px solid var(--sun)` + `box-shadow:0 0 0 1px var(--feel-focus-halo)`), each paired with `:focus{outline:none}` (`:39-41`) so a MOUSE click never shows the ring. ENFORCED, not asserted: `npx vitest run src/design/feel-focus.test.ts` = green (ran 2026-06-13) — its tests "every control-bearing shell component consumes the feel-focusable ring" and "no shell control uses a BARE :focus border" both pass, and the dual-tone legibility test proves best-of-{sun,halo} ≥ 3:1 over black/white/ice-1/charcoal-2. index.css carries 0 hex literals + 0 raw radii (`grep -cE '#[0-9a-fA-F]{3,6}' = 0`, `grep -cE 'border-radius:[0-9]' = 0`). The F-1 z-stacking kill (SPR-08 commit) is in GlassSurface (`apps/reading/src/shell/GlassSurface.tsx:123-124` opaque-fill, no colour jump).
- **Scene: 3/3 (held)** — `scene.css` declares motion only, 0 hex + 0 raw radii (`grep -c` both = 0). Geometry/colour from tokens. A 7th layer appeared since baseline (`apps/reading/src/scene/layers/Mountainscape.tsx`; baseline listed 6) — still hex-clean at the CSS layer.
- **Werner: 2*/3 (named exception)** — colours token-sourced (`apps/reading/src/werner/ice-fishing.css` + `waddle.css` both 0 hex). NAMED JUSTIFIED EXCEPTION: Werner is a mascot, not a control — it exposes no interactive `:focus-visible` control of its own, so it cannot reach the level-3 state-pair-border refinement bar. Tokenized-but-not-control-refined = the gate's permitted 2-with-named-exception, carried from baseline unchanged.
- **Reading-mode: 2/3 (held)** — reading surfaces consume tokens; focus coverage partial (HouseSlot carries `feel-focusable`/`focus-visible`; not uniform across reading controls). Genuine 2, not an exception.
- **Fallback: 3/3 (held)** — crispness HOLDS scene-off: `--glass-bg-solid` opaque fallback in both themes (`apps/reading/src/design/tokens.css`), GlassSurface renders the opaque solid with no backdrop-filter under reduced-motion. `tokens.contrast.test.ts` green (ran 2026-06-13). 3-level radius scale (`tokens.css:182-184`) + 4-level shadow scale (`:176-179`).

### Motion & life — 3/3 (held — verified no regression from combining sprints)
The dimension most at risk of a combine-regression (a new scene layer or a new Werner pose could introduce a rogue decorative keyframe or a layout-thrash transition). It did not.

- **Universal reduced-motion guard intact:** `apps/reading/src/design/motion.css:23-28` collapses ALL transition/animation duration to `0.01ms !important` under `@media (prefers-reduced-motion: reduce)` — SYSTEMIC, stronger than PostHog's 2-of-53 per-component.
- **Keyframe budget GPU-cheap on the integrated tree:** scene.css = 3 keyframes; Werner = 22 (`waddle.css`/`ice-fishing.css` = 10 + `src/brand/werner/**` = 12). The only width/height in Werner CSS is STATIC element setup (`apps/reading/src/werner/ice-fishing.css:21-22` `.werner-ice-bait` is `position:fixed` sized once; its animation `werner-bait-bob` is transform-only) — NOT inside any keyframe. Zero layout-property animations.
- **Motion-guard ratchet at its strictest:** `apps/reading/src/design/motion/motion_guard_baseline.json` = `[]` (empty allowlist — zero grandfathered raw-keyframe violations); `motion.guard.test.ts` green (`npx vitest run src/design/motion` = passed 2026-06-13).
- **Choreographed enter AND exit on transient surfaces** (`WorkspaceWindow.tsx`, `PanelLayoutPanel.tsx` paired transform+opacity exit, reduced-motion-aware at the call site). Named motion tokens single-source (`tailwind.config.js` ← `src/design/motion.ts`).
- **Living-scene exception honored:** ambient always-on motion is the NAMED, JUSTIFIED living-scene exception (rubric Dimension 2 logged DECISION); freezes under reduced-motion, asserted in `apps/reading/e2e/glass-reduced-motion.spec.ts`.
- **LIVE-ART caveat (awaiting operator, SPR-09 M2/M3):** the Krea live-art crossfade in MOTION cannot be observed without a live token. The procedural/fallback motion (scene freeze + opaque legible frame) IS observable and graded 3/3. The live-art-active confirmation is recorded as awaiting operator activation; it does NOT block this 3 — the graded surface (procedural floor + scene/werner/shell motion) is first-class and complete.

### Product character — 1/3 (FLOOR: reading-mode 1; the MISS)
Werner genuinely lifted; the reading-mode floor did NOT. The dimension rolls up to its floor.

- **Werner: 3*/3 (was 2)** — SPR-07 closed the baseline gap ("0 co-located Werner stories"): `apps/reading/src/brand/WernerScene.stories.tsx` ships **2 named state-authored stories** (`grep -cE '^export const ' = 2`): `SceneRestingPoses` (`:57`, authors a cue for all 8 scene states) + `DelightMoments` (`:117`). Backed by a total 8/8 `SceneMood→pose` map (`wernerSceneMap.ts`) + 4 deterministic delight moments (`wernerMoments.ts`), tests green (`npx vitest run src/brand/wernerSceneMap.test.ts src/brand/wernerMoments.test.ts` = passed). NAMED JUSTIFIED EXCEPTION (the `*`): there is NO daypart-distinct standing-pose ART — `POSE_GAPS` (`apps/reading/src/brand/wernerSceneMap.ts:96`) records 6 honest gaps; the resting pose is `idle` day and night. The bespoke daypart art is operator+Krea, out of scope (recorded, not faked).
- **Reading-mode: 1/3 (UNCHANGED — the gate miss).** The rubric grades this dimension on **Storybook state-authorship + co-location**, and its level-1 absence anchor is "exactly 1 named story for a component with ≥2 meaningful states." On the integrated tree that anchor STILL fires on TWO reading-mode components: `apps/reading/src/modes/Reading/ResearchThis.stories.tsx` ships **1** named story (`Default`, `:21`) for a component with ≥3 states (idle/busy/error — `ResearchThis.tsx:34-35,68` `busy`+`error` + happy); `apps/reading/src/modes/Reading/VoiceNote.stories.tsx` ships **1** named story (`CapturePhase`, `:22`) for a component with ≥6 states (`VoiceNote.tsx:26` `Phase = "capture"|"transcribing"|"correcting"|"saving"|"saved"` + an error state at `:32`). Neither file was touched by ANY ALC elevation sprint (`git log -1` on both = `748a5ec3`, the original Read feature commit — not the SPR-05..08 commits). The loading/empty/error states SPR-07 authored (live regions + §5 copy on Reading/index, PersonalSpace, MetaReading) are REAL craft and are TEST-asserted — but they are runtime states asserted in `*.test.tsx`, NOT authored as named, co-located Storybook stories (verified: `find Reading -name 'index.stories.tsx'|'Reading.stories.tsx'|'PersonalSpace .stories'|'MetaReading .stories' = none`). The rubric's countable criterion is Storybook authorship; on that criterion the floor is unmoved.
- **Scene: 2/3 (held)** — 0 co-located `*.stories.tsx` for the scene layers; states authored/asserted in e2e + the SPR-05 mood-matrix artifact, not Storybook-inspectable per layer. Above L1, below L3 = 2.
- **Shell: 2/3 (held)** — control-bearing co-location 5/6 (SceneChrome missing a story) < 85% L3 bar; NavRail authors 6 named states (3-caliber) but ProductsLauncher authors 1. ≥2 named with ≥1 non-default but below 85% = 2.
- **Fallback: 3/3 (held)** — the fallback is an authored, asserted e2e state (`glass-reduced-motion.spec.ts`).

### Evidence-backed craft — 2*/3 (held; named exceptions)
Both rails present; the dimension caps at 2 on RAIL-A rigor + RAIL-B depth. No regression from combining sprints; one POSITIVE integrated change (the Storybook build, broken at SPR-08's grading point, is now repaired).

- **RAIL A (Lost-Pixel image-snapshot): present-but-weak = 2.** `find apps/reading/.lostpixel/baseline -name '*.png' | wc -l` = **381** committed baselines. NAMED EXCEPTIONS (carried, recorded honestly): (1) effectively SINGLE-THEME — only **3** baselines carry a dark/night variant (`grep -iE 'night|dark'` = 3); (2) FLAGSHIP EXCLUDED — `apps/reading/lostpixel.config.ts:51-53` `filterShot` skips `workspace-demo--scene` (framer-motion spring nondeterminism), so the living-scene centerpiece is not pixel-gated; (3) NON-BLOCKING in CI — `.github/workflows/visualtest.yml:60` runs `npx lost-pixel || echo "::warning…"` (informational until baselines are dashboard-approved). The Lost-Pixel re-mint to a reference env is operator-deferred.
- **RAIL A2 (axe a11y gate): real hook, CI-informational — NOT a combine-regression.** `apps/reading/.storybook/test-runner.ts:69,90` still THROWS on serious/critical (`BLOCKING_IMPACTS = {"serious","critical"}`). But the CI workflow that runs it is INFORMATIONAL (`visualtest.yml:131` `|| echo "::warning…getIndexJson…"`). IMPORTANT: this informational state was ALREADY TRUE at the baseline SHA `16ff381d` (the comment block is byte-identical via `git show 16ff381d:.github/workflows/visualtest.yml`) — it PREDATES the elevation sprints and is therefore NOT a regression introduced by combining them. The baseline-2026-06-12 run-A characterized axe as "the only blocking-by-design visual gate," which was generous to the CI wiring; the hook code blocks, the CI wiring does not — at baseline AND now. `scripts/a11y_audit.ts` (exits non-zero on serious/critical) exists and is wired to `npm run a11y:audit` but is NOT invoked by any `.github/workflows/` file as a blocking step. Net: no delta on axe enforcement between baseline and final.
- **RAIL B depth: shallow = caps at 2.** `apps/reading/src/components/lemon/LemonButton.stories.tsx` = **4** named exports (`grep -cE '^export const '`) vs PostHog's 23 — unchanged, no loading/active/side-action cross-product.
- **POSITIVE integrated delta (Storybook build repaired):** at SPR-08's grading point `build-storybook` was RED on the SPR-07 file `WernerScene.stories.tsx` (csf indexer "Unexpected token (77:3)"). On the final integrated tree the block-body fix is in place (`WernerScene.stories.tsx:58-60` "ALC SPR-08, fixing inherited SPR-07 build-storybook break") and `npm run build-storybook` SUCCEEDS (built in 7.88s, ran 2026-06-13). This makes the entire story-based evidence layer inspectable again — it strengthens the dimension's substrate without changing the 2 (the RAIL-A/RAIL-B caps are independent of the build).
- **Scene: 2*/3** — flagship `workspace-demo--scene` excluded from RAIL A; enforced behaviorally (`glass-reduced-motion.spec.ts`) + the motion-guard ratchet. Present-but-flagship-excluded = 2.
- **Fallback: 3/3 (held)** — enforced on its OWN dedicated real-browser gate (`glass-reduced-motion.spec.ts` forces reducedMotion:reduce, asserts painted-not-flat + WCAG-AA over the opaque fallback).
- **TS strict + integrated suites green** (substrate the grades rest on): `npx tsc -b` exit 0; the design/scene/shell/werner vitest suites green (feel-focus 22, motion+werner 33, all ran 2026-06-13).

---

## NAMED JUSTIFIED EXCEPTIONS (carried from the sprints — recorded, gate-clause-compliant where the dimension passed)

1. **Werner daypart-standing-art gap (POSE_GAPS).** No daypart-distinct standing-pose ART; resting pose is `idle` day and night. `apps/reading/src/brand/wernerSceneMap.ts:96` records 6 honest gaps. Operator+Krea art, out of scope. This is the named exception that lets Werner clear product character at 3* and visual crispness at 2* — NOT a claim of distinct day/night standing art (which does not exist and is not faked).
2. **Evidence-craft RAIL-A non-blocking + single-theme + flagship-excluded.** 381 committed Lost-Pixel baselines, but informational-in-CI (`visualtest.yml:60`), effectively single-theme (3 dark of 381), flagship `workspace-demo--scene` excluded (`lostpixel.config.ts:51-53`). The Lost-Pixel re-mint to a reference env is operator-deferred. Caps evidence-craft at 2* — a permitted 2-with-named-exception.
3. **build-storybook was just repaired (SPR-08).** The inherited SPR-07 csf-indexer break is fixed on the integrated tree; `build-storybook` now succeeds. Recorded as a POSITIVE integrated delta (not an open exception) — the story-evidence layer is inspectable again.
4. **Live-art-active confirmation awaits operator (SPR-09 M2/M3).** No live Krea token in this env; the live-art crossfade in motion is unobservable. The procedural/fallback floor (graded first-class) IS observable and complete. Recorded as awaiting operator activation; does not block any grade — the procedural surface is the designed first-class state, not a degradation.

---

## STABILITY — do the integrated grades agree within ±1 with the per-sprint audits?

Read the four per-sprint audits AFTER forming the grades above. Side-by-side on the dimension roll-ups:

| Dimension | baseline | SPR-05 | SPR-06 | SPR-07 | SPR-08 | THIS (integrated) | Within ±1 of all? |
|---|---|---|---|---|---|---|---|
| Visual crispness | 1 | 1 | 1 | 1 | 2 | **2** | YES |
| Motion & life | 3 | 3 | 3 | 3 | 3 | **3** | YES |
| Product character | 1 | 1 | 1 | **3** | 1 | **1** | **NO — SPR-07 diverges by 2** |
| Evidence-backed craft | 2 | 2 | 3 | 2 | 2 | **2** | YES (SPR-06's 3 is a scoped scene-only cell, dimension floor still 2) |

**DIVERGENCE FLAGGED (>±1): Product character, SPR-07 = 3 vs integrated = 1 (a 2-level gap on identical code).** This is the rubric-stability flag the AUDITOR demands. The disagreement is an INTERPRETATION split on what "the reading-mode surface" means for Dimension 3:
- SPR-07's audit re-defined reading-mode product character as the reading-surface SYSTEM STATES (loading/empty/error live regions, §5 copy, test-asserted) and graded reading-mode 1→3.
- The baseline AND the SPR-08 audit (both grading the same post-SPR-07 tree, since SPR-08 sits off integration `db0f8556`) held reading-mode to the rubric's LITERAL countable criterion — Storybook co-location + named-story-per-meaningful-state — and graded it 1, citing `ResearchThis.stories.tsx`/`VoiceNote.stories.tsx` each at 1 named story.

The rubric's text is decisive against SPR-07's reading: Dimension 3 is "Graded on **Storybook state-authorship and co-location ratio**," and its level-1 anchor is verbatim "exactly 1 named story for a component with ≥2 meaningful states … never inspectable in isolation." SPR-07's runtime live-region states are genuine craft but are NOT named Storybook stories; they do not clear the countable bar the rubric names. The SPR-07 grade was INFLATED relative to the rubric's own discriminator. The integrated grade (1) agrees with baseline + SPR-05 + SPR-06 + SPR-08 (four of five prior reports) and is the defensible one.

Per the AUDITOR stability rule, the >±1 divergence is a flag on the RUBRIC's discriminating power for this surface — the anchor was loose enough to let one auditor count test-asserted runtime states as "state authorship." The CODE did not change between SPR-07's grading and SPR-08's; only the interpretation did. But the rubric flag does NOT rescue the gate: under the rubric's LITERAL criterion (the one the gate cites), product character is 1, and 1 fails the SPR-09 all-four bar.

---

## DID ANY DIMENSION REGRESS WHEN THE SPRINTS COMBINED? (the adversarial question)

**No dimension regressed below its 2026-06-12 baseline on the integrated surface.** Attacks tried and their results:

- *Did a new scene layer (Mountainscape) or new Werner poses introduce a rogue decorative keyframe / layout-thrash, dropping motion below 3?* — NO. Keyframe budget GPU-cheap, motion-guard baseline empty (`[]`), universal reduced-motion guard intact, motion tests green.
- *Did SPR-08's z-index/glass migration break the SPR-05/06 scene crispness or SPR-07 Werner wiring?* — NO. Scene CSS still 0-hex; Werner state tests green; tsc clean.
- *Did the focus-ring dual-tone upgrade or the feel-focusable rollout regress any shell control to a bare `:focus`?* — NO. The "no bare :focus" test passes; the baseline's named ProductsLauncher embarrassment is fixed.
- *Did the axe gate silently go from blocking to informational when sprints merged (an evidence-craft regression)?* — NO. It was ALREADY informational at the baseline SHA; no delta.
- *Did product character DROP below baseline?* — NO. It stayed AT baseline (1). The miss is a NON-LIFT, not a regression: SPR-07 lifted Werner (2→3) but did not lift the reading-mode floor (1→1), and the dimension rolls up to its floor.

The capstone failure is therefore not "the sprints broke something when combined." It is "the product-character dimension never cleared its baseline floor, because the owning sprint (SPR-07) authored runtime states instead of the named Storybook stories the rubric counts, and its self-audit graded itself against a looser interpretation than the gate's literal criterion."

---

## Fairness notes (where Antiek meets or beats PostHog)
- **Motion & life:** SYSTEMIC reduced-motion (one universal guard, `motion.css:23-28`) vs PostHog's 2-of-53 per-component; named duration/easing tokens single-sourced. Legitimate 3/3.
- **Visual crispness (token depth + shell coverage):** 4-level shadow scale + WCAG-AA baked into tokens with an automated test, AND now full feel-focusable shell coverage with a passing coverage test — the integrated shell 3 is defensible and verified, not asserted.
- **Evidence-craft (enforcement breadth):** axe hook + motion-guard ratchet + e2e experience/resilience matrices + 381 Lost-Pixel baselines — Antiek BEATS PostHog on enforcement breadth; it TRAILS on RAIL-A rigor (theme matrix + blocking CI + flagship inclusion), not the rail's existence.
- **Product character (Fallback):** the procedural/degraded state is an authored, ENFORCED, first-class e2e experience — 3/3, the discipline the rubric grades as first-class.

## Honest embarrassments (the before-photo's job — the capstone keeps it honest)
- **Product character / Reading-mode 1/3 — the capstone MISS.** `ResearchThis.stories.tsx` + `VoiceNote.stories.tsx` each ship one happy-path story for components with ≥3 and ≥6 states. Untouched by every elevation sprint. The dimension does not beat its baseline; the SPR-09 all-four gate FAILS here. Recorded without softening: the capstone does NOT ship this with an asterisk — it loops SPR-07.
- **SPR-07's self-audit inflated product character by 2 levels** vs the rubric's literal Storybook-co-location criterion (3 vs 1). The integrated grade agrees with four of the five other reports. Flagged as a rubric-anchor looseness AND as the reason the gate was thought met when it was not.
