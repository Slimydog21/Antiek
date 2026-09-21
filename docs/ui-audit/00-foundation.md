# 00 — Foundation: the design system itself

Audit of `apps/reading/src/design/`, `apps/reading/src/index.css`, and the lint
scripts (`lint_tokens.ts`, `lint_type_scale.ts`, `check_token_parity.ts`),
against the repo's own contract (`DESIGN_LANGUAGE.md`, `FEEL_CONTRACT.md`)
first, general craftsmanship second. Read-only audit; `npm run lint:tokens`
and `npm run lint:type` were run from `apps/reading` (both green — see
findings F4/F5 for what "green" hides). All grep counts verified on
2026-09-20 against branch `ui/posthog-grade-polish`.

## Surfaces

### tokens.ts — canonical token module
Entry: `apps/reading/src/design/tokens.ts:1`. The TS source of truth: `sun`
(brand constant + re-toned weathered `deep`/`glow`/`highlight`), `sunLight`,
`rule`, `barAccent`, `glass`, the 10-step day/night `surface` ramps +
`aliasFor()`, chunky `shadow` tiers, `werner` mascot palette, `accent`
(aurora/emperor), `state` research-state aliases, `motion` duration/easing
scale (80/150/800ms), `pitch`, `linkMonster`, `radius`, `edgeWidth`, `type`.
Exceptionally well-documented — every re-tone carries its WCAG math. But the
TS side is barely consumed: only ~10 importer files (mostly sketches/arcade);
`barAccent`, `glass`, `radius`, `edgeWidth`, `state` have zero non-design
importers. The app resolves colour through Tailwind classes and CSS vars
instead — which is exactly where the phantom-token problem (F1) lives.

### tokens.css — CSS-var sibling
Entry: `apps/reading/src/design/tokens.css:1`. Mirrors tokens.ts as custom
properties: day `:root` block, night `@media (prefers-color-scheme: dark)`
block that *re-maps the day ramp names* (`--ice-0` becomes `#1B202A` at
night, lines 244-246), glass, werner (incl. `--werner-rod`/`--werner-fish`),
state aliases, shadows, geometry, density (`--spacing`, `[data-density]`),
opacity, motion, and the feature-scoped `--lm-*` Link Monster block
(lines 366-387). Imported by `main.tsx:5` and `.storybook/preview.tsx:9`.
Carries several defined-but-never-referenced vars (F10).

### DESIGN_LANGUAGE.md — the human contract
Entry: `apps/reading/src/design/DESIGN_LANGUAGE.md:1`. The operating manual:
"function, not taste," §5.6 (borrow PostHog forms, keep Werner skin), five
principles, canonical token list, token-lint policy ("the baseline only ever
shrinks"). Accurate in philosophy; stale in specifics — it lists pre-SPR-09
hexes as canonical (F3), a stale grandfathered count, and pre-rename radius
names (F9, F19).

### FEEL_CONTRACT.md — elevation contract
Entry: `apps/reading/src/design/FEEL_CONTRACT.md:1`. The dual-store chrome
contract: opaque-chunky cards vs glass-scene windows, hover-lift, ≥20px
cascade, focus ring, z-layer diagram (toast 200 / modal 100 / panels 2-50 /
windows ≥40), exemptions. The layer diagram is incomplete vs `zIndex.ts`
(F14); otherwise consumers (`PanelLayoutPanel.tsx:141`,
`WorkspaceWindow.tsx:247`) honour it.

### elevation.ts — stack depth → shadow tier
Entry: `apps/reading/src/design/elevation.ts:1`. Pure data module:
`shadowForStackDepth`, `cascadeOffset` (windows 28px/224 wrap; panels
22px/200 wrap — both ≥20px per contract), `opaquePanelShadowClasses`,
`FLOATING_Z_BASE` sourced from `zIndex.ts`, `ELEVATION_EXEMPT_SURFACES`.
Well-tested (`elevation.test.ts`). The `ChromeMode` parameter is dead — both
branches return the same array (F13); one misplaced docstring (F13).

### motion.ts + motion.css + motion/ — the motion system
Entries: `apps/reading/src/design/motion.ts:1`, `motion.css:1`,
`motion/README.md:1`, `motion/sceneMotion.ts:1`. `motion.ts` defines three
class-string primitives (`press`, `cardLift`, `enter`) + `durationMs`;
`motion.css` is the global reduced-motion catch-all (imported `main.tsx:7`);
`motion/README.md` defines the "allowed slots" and the anti-noise keyframe
guard (baseline currently 0 — clean). Adoption is thin and uneven: `press`
has 2 consumers (LemonButton, PanelHandle), `cardLift` 3, `enter` **zero**
(F8); `sceneMotion.ts` runs a 1200ms crossfade over the 800ms token ceiling
(F11).

### feel-focus.css — keyboard focus bundle
Entry: `apps/reading/src/design/feel-focus.css:1`. Two classes
(`.feel-focusable`, `.feel-focusable-ring`) giving a `var(--sun)` focus
outline/ring. Imported in `main.tsx:6`. **Zero consumers anywhere in src** —
the shipped focus pattern is ad-hoc Tailwind `focus-visible:ring-*` (F7).

### zIndex.ts — the named z ladder
Entry: `apps/reading/src/design/zIndex.ts:1`. Frozen ladder (raised 1 →
toast 200) + `Z_LADDER_ORDER` + `forceAbove`, pinned by `zIndex.test.ts`.
Honest about being a catalogue, not a migration: `z-[100]`/`z-[200]`/
`z-[150]`/`z-[60]` literals still live at the catalogued call sites
(`LemonModal.tsx:103`, `LemonToast.tsx:132`, `AdBorder.tsx:160`,
`PenguinMascot.tsx:566`). `forceAbove` unused (F15).

### index.css — global sheet
Entry: `apps/reading/src/index.css:1`. Tailwind directives, the pdf.js text
layer (`.pdf-text-layer`, opacity 0.18), and token-driven `::selection`
highlighter rules (day/night via `--sun-hl-*`). Clean, token-driven — except
the debug-opacity text layer that dims its own selection highlight (F12).

### lint_tokens.ts + token_lint_baseline.json — "every colour is a token"
Entry: `apps/reading/scripts/lint_tokens.ts:1`. Fails CI on any *new* raw hex
outside tokens.ts/tokens.css; grandfathered baseline. Currently green:
**80 live literals vs a 120-entry baseline** — 37+ stale entries, all from
Werner SVG fills already migrated to tokens (F4). The lint also cannot see
phantom token *names* (F1) or `rgba()` literals (F16).

### lint_type_scale.ts + type_scale_lint_baseline.json — 24px chrome ceiling
Entry: `apps/reading/scripts/lint_type_scale.ts:1`. Fails on new
`font-size: NNpx` / `text-[NNpx]` above 24px outside reading-content dirs.
Green, with 0 live violations vs a 1-entry stale baseline (F5). Governs only
the ceiling: **1,033 arbitrary sub-ceiling `text-[Npx]` across 180 files**
are ungoverned (F6).

### check_token_parity.ts — sun accent/shadow drift guard
Entry: `apps/reading/scripts/check_token_parity.ts:1`. Asserts tokens.css
still carries the weathered SPR-09 values and that tailwind.config.js's
`sun-deep`/`sun-glow`/`*-night` shadow keys reference `var(--sun-deep)` etc.
rather than hardcoded hexes. Currently satisfied (tailwind.config.js:32-33,
111-114). Narrow: covers only the sun family; `rule`/`bar-accent`/`glass`
parity is unguarded, and it hardcodes a third copy of the hexes (F17).

## Findings

| Severity | Location | Issue | Fix direction |
|---|---|---|---|
| P0 | `tailwind.config.js:15-95` (resolution layer) + consumers e.g. `PanelWindowApp.tsx:123`, `Library/index.tsx:296`, `BrainstormStation/ThoughtPartnerPanel.tsx:211`, `LineupPitch.tsx:121` | **Phantom token utilities at scale.** `text-ink-mute` ×362 class refs (98 files), `text-ink-soft` ×240, `ocean` ×62 (`border-ocean`, `bg-ocean/10`, `ring-ocean`, `var(--ocean)` — defined *only* in the `public/redesign.html` mock), `bg-sun-light`/`dark:text-sun-light`/`bg-sun-light-soft`, `bg-card` ×15 / `bg-inset` ×32 alias classes — none resolve: no Tailwind color key, no CSS var. Tailwind v3 generates nothing for them; the app's dominant muted-text and one whole accent colour are silent no-ops. The foundation lints enforce "no raw hex" but never "referenced token exists." | Add a referenced-token-resolution guard (scan class names + `var(--*)` refs against tokens.css/tailwind.config.js). Define `ink-mute`/`ink-soft` (likely == `shadow-1`/`--text-muted`) or codemod consumers; resolve `ocean` to a brand accent or delete it. |
| P0 | `src/design/moodboard.stories.tsx:122` and `:57` | The operator-signed visual reference displays **retired, WCAG-failing hexes as canonical**: emperor swatch `#E33C2D` (superseded by `#CE3623` in SPR-01 for the 4.5:1 floor) and night shadow `#8A7300` (superseded by `#84722F` in SPR-09). The moodboard is DESIGN_LANGUAGE.md's "visual gate" — it currently teaches the wrong palette. | Read `accent.emperor.day` / `shadow.night` from tokens.ts instead of literals; sweep the file's other 56 literals the same way. |
| P0 | `src/design/DESIGN_LANGUAGE.md:48` | The human contract still lists `sun-deep #B89A00 (day) / #8A7300 (night)` as canonical brand tokens — the pre-SPR-09 loud values, contradicting `tokens.ts:53` (`#9C8636`/`#84722F`) and the file's own SPR-01 reconciliation section. The SPR-09 re-tone and the entire `sunLight`/`rule`/`barAccent` families are absent from the canonical-tokens section. | Update §Canonical tokens to the weathered values; add sunLight/rule/barAccent/glass with one-line roles. |
| P1 | `scripts/token_lint_baseline.json:2-121` | **Baseline is stale by 40 entries** (120 entries vs 80 live literals; `npm run lint:tokens` prints the discrepancy). 37 dead entries are Werner SVG fills since tokenised — each silently re-permits that exact file+hex combo forever. Violates the file's own "baseline only ever shrinks" policy (`lint_tokens.ts:9-10`, DESIGN_LANGUAGE.md:70). | Deliberate `--update` re-mint (reviewed, per policy); add a CI assertion that baseline length == live count so drift is loud. |
| P1 | `scripts/type_scale_lint_baseline.json:2` | Stale entry: `src/modes/Login/index.tsx text-[26px]` no longer exists (0 live violations). Same shrink-policy violation as F4. | Re-mint; same count-parity CI check. |
| P1 | `scripts/lint_type_scale.ts:60,74-75` | The lint governs only the >24px escape hatch. Below the ceiling, **1,033 arbitrary `text-[Npx]` in 180 files** (histogram peaks: 11px ×345, 10px ×267, 12px ×192, 13px ×138 — none on the named xxs/xs/sm scale; 15 uses of 9px sit *below* the xxs=10px floor) vs ~1,000 named-scale uses. `LinkMonster.css` alone carries 21 raw `font-size:` declarations (9-17px, e.g. lines 46, 203, 273). Half the app's type is off-scale and the lint is blind to it. | Extend the lint (baseline-grandfathered) to arbitrary sub-ceiling sizes, or codemod the four hot values (10/11/12/13) onto `text-xxs/xs/sm` and ban the rest. |
| P1 | `src/design/feel-focus.css:5-19` | Imported globally (`main.tsx:6`) but **zero consumers**: no element carries `.feel-focusable` or `.feel-focusable-ring`. The de-facto focus pattern is scattered `focus-visible:ring-2` ×12 / `ring-sun` ×8 / `ring-ocean` ×4 (phantom) / bare `focus:outline-none`. FEEL-S5's "one focus ring" contract is unmet; `feel-focus.test.ts:30-45` only guards three dirs for outline-none pairing. | Either adopt the bundle on Lemon primitives + panel/window chrome, or delete it and standardise on `focus-visible:ring-2 ring-sun`; kill `ring-ocean`. |
| P1 | `src/design/motion.ts:62-65` | The `enter` primitive (panel/modal fade-rise) has **zero consumers** — its own comment admits "not yet wired." Meanwhile ≥10 files hand-roll hover lifts (`hover:-translate-*`: `Home.tsx`, `Biography/index.tsx`, `LemonSelect.tsx`, `ModelPicker.tsx`, `LineupPitch.tsx:250` …) and CSS files use off-token durations (StyleWheel.css:8 `160ms`, Login.css:33 `90ms`, brainMascot.css:27 `120ms` vs the 80/150/800 scale). The "one vocabulary, not re-improvised" rule (motion/README.md:33-35) holds only where someone remembered. | Wire `enter` into LemonModal/PanelLayoutPanel; codemod hand-rolled lifts to `press`/`cardLift`; extend the motion guard to non-token durations. |
| P1 | `src/design/tokens.css:33,134,140,187` + `tokens.ts:140,168,324,374,377` | **Defined-but-unused tokens** accumulate: CSS vars `--sun-light-soft`, `--werner-rod`, `--werner-fish` (long justification comments, zero references), `--density` (documented as reserved), `--page`/`--divider`/`--muted` vars (0-2 refs); TS exports `barAccent`, `glass`, `state`, `radius`, `edgeWidth` with zero runtime importers. The contract says every element must earn its place by work done — these do no work. | Wire them or delete them; add a "defined-but-unreferenced" report to check_token_parity or a new lint. |
| P1 | `src/design/motion/sceneMotion.ts:19,32-36` | `CROSSFADE.durationMs = 1200` exceeds the motion scale's `slow` ceiling (800ms, tokens.ts:354; "no flourish may run longer"), and the ambient DRIFT loops (31-67s periods) are not one of the four "allowed slots" in motion/README.md:30-58. The design dir's own scene layer lives outside the motion contract it hosts. | Either document scene ambience as an explicit fifth slot with its own bounds, or route crossfade through the token scale. |
| P1 | `src/index.css:13` | `.pdf-text-layer` ships `opacity: 0.18` with the comment "visible enough to debug" — a debug value in production. Because the `::selection` highlight lives *inside* that layer (index.css:21-28), the operator's 0.45-alpha highlighter renders at ~0.08 effective alpha on PDFs — nearly invisible, contradicting the highlighter contract the same file implements. | `opacity: 0` (spans are already `color: transparent`, line 45) or a documented non-debug rationale. |
| P2 | `src/design/elevation.ts:54-61` | `shadowForStackDepth`'s `ChromeMode` parameter is dead: the `glass-scene` and `opaque-chunky` branches return the identical array — the "title-bar only" glass differentiation lives entirely in the consumer (`WorkspaceWindow.tsx:247`). Also a misplaced docstring (:80, describes `ELEVATION_EXEMPT_SURFACES` but sits above `opaquePanelShadowClasses`) and an orphaned comment block (:26-29). | Drop the mode param (or give glass a real mapping); reattach the docstring. |
| P2 | `src/design/FEEL_CONTRACT.md:15-25` | The layer diagram omits four ladder rungs that `zIndex.ts:62-97` catalogues: sceneBadge 5, mascot 60, popover 120, adOverlay 150. Two layering documents disagree in completeness; the contract is the one humans read. | Regenerate the diagram from `Z_LADDER_ORDER` so there is one picture. |
| P2 | `src/design/zIndex.ts:128` | `forceAbove` — the documented escape hatch — has zero consumers outside tests. | Delete or wire. |
| P2 | `scripts/lint_tokens.ts:40-42` | Documented blind spot (all-numeric short hexes like `#333`) plus an undocumented one: `rgba()`/`hsl()` literals are never scanned — 7 in components, e.g. `LineupPitch.tsx:250` `shadow-[2px_2px_0_rgba(0,0,0,0.15)]` hand-rolls a shadow outside the `shadow-z*` system and dodges the lint. | Extend the regex (or add an rgba/hsl pass); migrate that shadow to a tier. |
| P2 | `scripts/check_token_parity.ts:60-65` | Parity is asserted only for the sun family; `rule`, `bar-accent`, `glass`, ice-ramp values can still drift silently between tokens.ts / tokens.css / tailwind.config.js (the known `border-rule` day-only limitation, tokens.css:258-264, is one such). `EXPECTED_CSS` also hardcodes a third copy of the hexes it guards. | Widen the guard to all mirrored families; derive expectations from tokens.ts. |
| P2 | `src/design/tokens.css:244-246` vs `tailwind.config.js:61-87` | Two parallel night strategies: CSS *re-maps* `--ice-*` names to night values while Tailwind `ice-*` classes stay day-static and components pair them with `dark:bg-charcoal-*`. A `var(--ice-1)` consumer and a `bg-ice-1` consumer diverge after dark. Documented in comments but structurally fragile. | Pick one strategy per token family and say so in DESIGN_LANGUAGE.md. |
| P2 | `src/design/DESIGN_LANGUAGE.md:26,52,67` | Doc drift: still says "the Werner penguin" (tokens.ts:283-306 renamed to the brain mascot, `WernerMood` deprecated); radius listed as `sm/hog/hog-lg` vs tokens.ts:374 `sm/md/lg`; "120 at mint" grandfathered count is now 80. | Refresh names + counts; keep §-number references stable. |
| P2 | baseline lines 49-58 → `src/components/AISidecar.stories.tsx`, `CommandPalette.stories.tsx`; `moodboard.stories.tsx:423-432` | Grandfathered Storybook swatches render the Tailwind **stone** palette (`#57534e`, `#78716c`, `#fafaf9`, `#e7e5e4`, `#d6d3d1`) — off-brand chrome in the visual reference app, incl. a "stone-200, the current UI" comparison block in the moodboard. | Migrate story mock chrome to Werner tokens; keep any intentional before/after block quarantined and labelled. |

## Verdicts

### tokens.ts — bring to standard:
1. Delete or wire the zero-consumer exports (`barAccent`, `glass`, `state`, `radius`, `edgeWidth`); keep `WernerMood` only until the deprecation window closes.
2. Add a docstring pointer that the *enforcement* gap is referenced-token resolution (F1), so the next reader knows "every colour is a token" is only half-guarded.

### tokens.css — bring to standard:
1. Remove or consume `--sun-light-soft`, `--werner-rod`, `--werner-fish`, `--density` (F10).
2. Resolve the dual night strategy for `--ice-*` vs Tailwind `dark:` classes (F18) — one rule per family, written into DESIGN_LANGUAGE.md.
3. Add the missing `--ink-mute` / `--ink-soft` definitions (or a codemod off them) as part of closing F1.

### DESIGN_LANGUAGE.md — bring to standard:
1. Correct §Canonical tokens to the weathered SPR-09 values; add sunLight / rule / barAccent / glass (F3).
2. Fix radius names, grandfathered count, penguin→mascot rename (F19).
3. Update the lint section to state the real current baseline (80) and the phantom-name blind spot.

### FEEL_CONTRACT.md — bring to standard:
1. Regenerate the layer diagram from `zIndex.ts` (`Z_LADDER_ORDER`) so all ten rungs appear (F14).
2. Note that `ChromeMode` currently does not change shadow output (F13) or fix elevation.ts and delete this note.

### elevation.ts — bring to standard:
1. Remove the dead `ChromeMode` branching or implement a real glass mapping (F13).
2. Reattach the misplaced `ELEVATION_EXEMPT_SURFACES` docstring (:80) to its export.

### motion system (motion.ts / motion.css / motion/) — bring to standard:
1. Wire `enter` into LemonModal + floating panels or delete it (F8).
2. Codemod the ~10 hand-rolled hover lifts and off-token CSS durations onto `press`/`cardLift`/the 80-150-800 scale (F8).
3. Bring `sceneMotion`'s 1200ms crossfade + ambient drift inside the contract — either as a documented scene-ambience slot or under the token ceiling (F11).

### feel-focus.css — bring to standard:
1. Adopt it on the Lemon primitives and panel/window chrome, or delete the file — dead CSS imported at the root is worse than none (F7).
2. Standardise focus rings on `ring-sun`; eliminate the phantom `ring-ocean` (Library/index.tsx:296,299,406,410).

### zIndex.ts — waive, with one fix:
The catalogue-not-migration stance is explicitly documented and test-pinned; the remaining `z-[100]`/`z-[200]`/`z-[150]`/`z-[60]` literals match the catalogue. Fix only: delete unused `forceAbove` or wire it (F15).

### index.css — bring to standard:
1. Drop `.pdf-text-layer` to `opacity: 0` or replace the debug comment with a real rationale — the current value dims the selection highlight it exists to show (F12).

### lint_tokens.ts — bring to standard:
1. Re-mint the baseline (120→80) per its own shrink policy, and add a baseline-length == live-count CI assertion so drift is loud (F4).
2. Add a referenced-token-resolution guard — the single highest-leverage gap; it would have caught ~670 phantom class/var references (F1).
3. Extend the colour scan to `rgba()`/`hsl()` literals (F16).

### lint_type_scale.ts — bring to standard:
1. Re-mint the stale 1-entry baseline (F5).
2. Extend coverage below the 24px ceiling: grandfather the 1,033 existing arbitrary sizes, then enforce named-scale-only forward — or codemod the 10/11/12/13px cluster onto `text-xxs/xs/sm` first and shrink the baseline at mint (F6).

### check_token_parity.ts — bring to standard:
1. Widen parity beyond the sun family to `rule`, `bar-accent`, `glass` (F17).
2. Derive `EXPECTED_CSS` from tokens.ts instead of a third hardcoded copy.

### moodboard.stories.tsx (design-dir resident) — bring to standard:
1. Replace the retired `#E33C2D` / `#8A7300` swatches with token reads (F2).
2. Migrate the 56 inline literals to token imports; quarantine the stone-palette "current UI" comparison block (F20).
