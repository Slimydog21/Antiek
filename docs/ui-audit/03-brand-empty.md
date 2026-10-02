# 03 — Brand and mascot integration

Scope: everything under `apps/reading/src/brand/` (BrainMascot, BrainMark,
BrainPresence, `marks/`, `mascotSceneMap.ts`, plus the `werner/` animated
wrappers that now delegate to BrainMascot), every render site of those three
components, the shared empty/failure surfaces (WorkflowStub, AIActionFailure,
LibraryView empty copy), and favicon/mark references in `index.html` +
`public/`. Audited against `src/design/DESIGN_LANGUAGE.md`,
`src/design/FEEL_CONTRACT.md`, `src/design/elevation.ts`, and
`src/design/motion.css`. Feature-art PR #3275 deliberately excluded (main
only). `npm run lint:tokens` run: green (80 grandfathered, baseline 120).

## Surfaces

### BrainMascot — canonical mark
Entry: `apps/reading/src/brand/BrainMascot.tsx:71`. One component mapping the
four-mood contract (`idle`/`thinking`/`empty`/`celebrate`, allowlist-enforced
with a dev runtime throw, `:83-92`) to Krea-generated transparent brain
rasters. Idle gets a JS-scheduled blink (crossfade to a closed-eyes frame,
`:99-116`), a CSS breathing sway (`brain-idle`), and a hover reaction.
Reduced-motion collapses via `useReducedMotion` + the media query in
`mascot-brain/brainMascot.css:49-58`. The header docblock (`:11-18`) still
advertises a cursor-follow tilt that was removed by operator directive (the
removal note is at `:118-120`); a `perspective: 600px` 3D context (`:129`)
and `.brain-tilt` preserve-3d wrapper survive as dead scaffolding.

### BrainMark — rail home logo
Entry: `apps/reading/src/brand/BrainMark.tsx:17`. Pure-vector geometric brain
(two hemispheres, sulcus, fold arcs, `fill-sun` spark) drawn with token
classes only — no hex, lint-clean. Purely presentational (`aria-hidden`); the
wrapping button in NavRail owns semantics. Rendered once, at
`shell/NavRail.tsx:361` inside the sun-filled home control (`:355-359`).
Cleanest surface in the audit.

### BrainPresence — ambient background brain
Entry: `apps/reading/src/brand/BrainPresence.tsx:30`. A 420px, opacity-0.08
idle BrainMascot pinned `right: -6%; bottom: -12%` behind app content,
`pointer-events: none`, with a 90s float keyframe
(`brainMascot.css:35-47`). Mounted once in `AppShell.tsx:137`, directly above
`<Scene/>`. Operator-ratified per its docblock. Two seams worth noting: an
uncatalogued inline `zIndex: 1` (`:48`) that collides in value with the named
ladder's `raised: 1` layer (`design/zIndex.ts:64`), and a docblock (`:13`)
claiming "pointer tilt" applies — it no longer exists.

### mascotSceneMap — scene → mood seam
Entry: `apps/reading/src/brand/mascotSceneMap.ts`. Pure data mapping
DayPart×Weather × live/fallback art to a mascot mood with `reason` and
`companionCopy` strings, plus a `POSE_GAPS` registry. Only
`mascotMoodForScene` is consumed (BrainMascot's `scene` prop, `BrainMascot.tsx:79`),
and no call site in the app passes `scene` — the seam is dead outside tests.
Every user-prose string still narrates "Werner" the penguin
(`:31-67`, `:152-155`) — aurora, snow, settled penguin — while rendering the
brain.

### brand/werner/animated wrappers
Entries: `WernerThinking.tsx:18`, `WernerSleeping.tsx:14`,
`WernerCaughtAFish.tsx:19`, `WernerWaddle.tsx`, `WernerTobogganSpinner.tsx`.
Thin motion wrappers that delegate the body to BrainMascot and add CSS chrome
via `animations.css`. WernerThinking (the AI-working signal, consumed by
AISidecar:323, shared/Thinking.tsx:44, Speak/index.tsx:403,462,
BrainstormStation/ThoughtPartnerPanel.tsx:270) adds four aurora dots styled
with hardcoded `#16C2C2` inline (`:37,46,55,64`) although the `aurora` token
exists (`tailwind.config.js:90`, `tokens.ts:310`). WernerCaughtAFish overlays
a penguin flipper holding an aurora fish plus a sun sparkle (`:36-52`) — with
hardcoded `#16C2C2`/`#EEF1F6` fills (`:45-47`) — on top of the *brain*;
penguin-lore chrome composited onto a penguin-free mascot.
WernerSleeping's zZz letters ride `var(--werner-coat)` — the penguin palette
tokens (`tokens.css:125-127`) are still the chrome vocabulary.

### werner/reactions/SemanticReactions
Entry: `brand/werner/reactions/SemanticReactions.tsx:96`. Four semantic emotes
(curious/happy/dizzy/hit) mapping to mascot moods with SVG chrome (evidence
card, verification stamp, paperclip orbit, brass tab) and per-kind durations
(800–1300ms, `:9-14` — all above the `motion.duration.slow` 800ms ceiling in
`tokens.ts:354`, though as one-shot beats they sit beside Werner's legacy
timings rather than the Lemon scale). Copy is brain-correct ("The brain
examines the evidence"). Consumed via `werner/emotes.tsx` on the project-home
station.

### Render sites (mascot placement)
- `shell/NavRail.tsx:361` — BrainMark 24px home control (the logo slot).
- `AppShell.tsx:137` — BrainPresence, always on, every route.
- `shell/PenguinMascot.tsx:596` — project-home station base mark, idle
  (ratified fishing-rig model, though BrainMascot's own docblock at `:24-26`
  falsely claims the station was "intentionally NOT re-skinned").
- `modes/Home/Home.tsx:65` — idle 72px hero on the landing; `:120` — a
  **persistent** celebrate-mood brain at 48px decorating the Biographies CTA
  card.
- `modes/Biography/index.tsx:99` — idle 52px header; `:255` — a **persistent**
  celebrate-mood brain on the post-creation success screen.
- `modes/SpeakIndex/index.tsx:122` — idle 44px header.
- `shared/delight/CelebrateBurst.tsx:46` — the one-shot celebrate beat
  (contract-correct usage).

### Shared empty / failure surfaces
- `shell/WorkflowStub.tsx:26` — the honest "not yet" surface: centred
  max-w-lg, mono uppercase eyebrow, serif h1 "Not yet — ⟨workflow⟩ is on the
  way.", pending-surfaces list. Type uses off-scale literals
  (`text-[11px]` :55/:73/:88, `text-[15px]` :79, `text-[13px]` :95). No
  mascot — the `empty` slot from the brand restraint rule goes unfilled here.
- `shared/AIActionFailure.tsx:55` — the one failure sentence every AI action
  shares: `role="alert"` + `aria-live="assertive"`, mono xs emperor text,
  framed "Engine:" diagnostic, LemonButton retry that never navigates.
  Consumed by Biography, SpeakIndex (:166), ResearchWorkstation, Write, etc.
  Correctly mascot-free (failure is not one of the four slots).
- `components/library/LibraryView.tsx:150-154` — honest empty copy
  ("Nothing here." / search / servable variants), no mascot, plain text.

### Favicon and marks
`index.html:9-11` — PNG-first icon chain: `/mark-32.png` primary,
`/favicon.svg` SVG fallback, `/mark-180.png` apple-touch-icon; all three
exist in `public/`. `public/favicon.svg` is byte-identical to
`src/brand/marks/brain-favicon.svg` — both embed the Krea raster as base64
PNG (deliberate, per the embedded comment). `index.html:14` sets
`<body class="bg-stone-50 text-stone-900 antialiased">` — Tailwind's default
stone palette, off the ice/ink token ramps. `public/redesign.html` is a
served static prototype with its own hardcoded palette duplicate.
`src/brand/marks/` + `src/brand/werner/marks/` hold duplicate out-of-app
derivative builders (`build_brain_marks.py` / `build_marks.py`, social cards,
avatars); the brain set's PROFILE.md (`mascot-brain/PROFILE.md:49-56`)
documents the palette with **wrong canonical values**: sun accent as
`#FFD54A` (canonical `sun.base` is `#F5DF24`, `tokens.ts`) and "app
`space-2`" as `#0B1020` (canonical space-2 is `#0D1019`, `tokens.ts:206`).

## Findings

| Severity | Location | Issue | Fix direction |
|---|---|---|---|
| P0 | `src/design/DESIGN_LANGUAGE.md:54` + `src/design/tokens.ts:279-297` | The design contract's canonical-token section still specifies "Werner mascot: coat = ink, belly = ice-1, bill + feet = sun" — the shipped mascot is the coral brain. The contract an audit runs against describes a mascot that no longer renders. | Rewrite the mascot token block for the brain (coral body, ink limbs, sun spark) or mark Werner tokens as legacy chrome-only. |
| P0 | `src/brand/README.md:3-13,38-60` | The brand directory's own README declares "Werner the penguin lives here" and names `src/brand/Werner.tsx` as the single source of truth — that file does not exist; BrainMascot.tsx does. The restraint rule and motion timings are Werner's. | Re-author the README around BrainMascot/BrainMark/BrainPresence; keep the four-slot restraint verbatim. |
| P0 | `src/modes/Home/Home.tsx:120` | Persistent `mood="celebrate"` brain as decoration on the Biographies CTA. The restraint rule (README:64-73) makes celebrate a one-shot completion beat; a permanent celebrate pose both burns the beat and violates "never more than one on screen" (BrainPresence is mounted on this same route). | Swap to `idle` or remove; reserve celebrate for CelebrateBurst. |
| P0 | `src/modes/Biography/index.tsx:255` | Persistent `mood="celebrate"` on the biography-started success screen — same one-shot violation; the screen lives as long as the route. | Use CelebrateBurst/useCelebrate for the beat, then idle or no mascot. |
| P1 | `src/brand/werner/animated/WernerCaughtAFish.tsx:36-52` | Penguin flipper + aurora fish SVG chrome composited over the brain mark; the celebration reads as penguin-lore on a penguin-free mascot. Hardcoded `#16C2C2`/`#EEF1F6` fills (:45-47). | Re-author the celebrate chrome for the brain (sparkle only, or a light-bulb/sun beat); route colours through `var(--aurora)`/tokens. |
| P1 | `src/brand/werner/animated/WernerThinking.tsx:37,46,55,64` | Four hardcoded `#16C2C2` inline-style fills though the `aurora` token exists in tokens.ts and tailwind.config.js. | `bg-aurora` class or `var(--aurora)`. |
| P1 | `apps/reading/index.html:14` | `<body>` carries `bg-stone-50 text-stone-900` — Tailwind default stone palette, off the ice/ink ramps; a flash of off-brand paint before React mounts. | Token classes (`bg-ice-2 text-ink`) or drop and let the shell paint. |
| P1 | `src/brand/mascotSceneMap.ts:31-67,152-155` | All reason/companion copy narrates "Werner" (penguin, aurora, snow) while rendering the brain; POSE_GAPS (:113-150) registry is penguin-era pose bookkeeping. | Re-write cues in brain voice; decide if the scene→mood seam survives at all (see P2 dead-prop below). |
| P1 | `src/brand/mascot-brain/PROFILE.md:55-56` | The brain's brand bible records wrong canonical values: sun accent `#FFD54A` (canonical `#F5DF24`) and "app space-2" `#0B1020` (canonical `#0D1019`). Future Krea generations will be colour-locked to the wrong brand. | Correct both to tokens.ts values and cite tokens.ts as source. |
| P1 | `src/brand/BrainPresence.tsx:48` | Inline `zIndex: 1` — an uncatalogued magic number that value-collides with the named ladder's `raised: 1` (docked panel layer) in `design/zIndex.ts:64`, against the ladder's "no magic numbers at call sites" destination. | Add a named `scenePresence` layer to zIndex.ts, or reuse `raised` deliberately with a comment. |
| P1 | `src/modes/Home/Home.tsx:125` + `modes/Biography/index.tsx` | Off-scale type: `text-[13.5px]` (Home:125) sits between pinned steps; h1s at `text-3xl` (Home:66, Biography:101,257) exceed the pinned scale's 2xl=24px chrome ceiling and disagree with sibling header SpeakIndex's `text-2xl` (SpeakIndex:124). | Pick one landing-h1 step (2xl or a sanctioned display token); replace 13.5px with `text-sm`. |
| P1 | `src/shell/WorkflowStub.tsx:55,73,79,88,95` | The honest-empty surface runs on off-scale literals (`text-[11px]`, `text-[15px]`, `text-[13px]`) instead of the pinned scale (xxs/sm/base). | Map to `text-xxs` / `text-sm` / `text-base`. |
| P1 | `src/shell/WorkflowStub.tsx:67-112`, `components/library/LibraryView.tsx:150-154` | The restraint rule reserves `mood="empty"` for blank/empty states, but no production empty surface renders it — the sleepy brain only appears via station emotes (`WernerSleeping`). The "empty" slot is dead in product. | Either wire the empty mood into WorkflowStub/first-run states, or amend the restraint rule to match reality. |
| P2 | `src/brand/BrainMascot.tsx:11-18,24-26,129,133` | Docblock drift: header still documents pointer-tilt and a hover "rotate wobble + scale bump" that don't exist (hover only forces a blink, :148); claims PenguinMascot was "NOT re-skinned" though it renders BrainMascot at PenguinMascot.tsx:596; dead `perspective: 600px` + `.brain-tilt` 3D scaffolding. | Rewrite the header to the shipped behaviour; delete the dead 3D context. |
| P2 | `src/brand/BrainPresence.tsx:13` | Docblock claims "blink + breathing + pointer tilt all apply" — tilt removed. | Edit the sentence. |
| P2 | `src/brand/BrainMascot.tsx:79` + `mascotSceneMap.ts` | The `scene` prop is never passed by any call site — mascotSceneMap is exercised only by tests. Dead public API carrying the P1 copy drift. | Wire it (rail mark reflects scene mood) or remove the prop + map. |
| P2 | `src/brand/mascot-brain/brainMascot.css:27` | Blink crossfade `transition: opacity 120ms ease` — off the motion scale (fast 80 / base 150 / slow 800, tokens.ts:350-360). | Use 150ms (`base`) or the `--motion-*` var. |
| P2 | `src/brand/BrainMark.tsx` vs `public/favicon.svg` | Two brand idioms for the same mark: geometric line brain (NavRail logo) vs Krea raster (favicon, mascot). Deliberate per comments, but the lockup is unwritten anywhere — drift risk. | One sentence in the brand README fixing which idiom owns which context. |
| P2 | `apps/reading/index.html` (head) | No og:/twitter: meta although `marks/social-card-1200.png` ships in both brain and penguin variants — the built card is unreachable. | Add og meta pointing at the brain social card (and publish it to `public/`). |
| P2 | `public/redesign.html:1-30` | A served static prototype with its own hardcoded palette duplicate (`--sun:#F5DF24` block) ships in `public/` — stale design fossil reachable in production builds. | Remove from public/ or move to docs/. |
| P2 | `src/design/tokens.css:125-127,314-316` + Werner wrappers | Chrome vocabulary still named `--werner-coat`/`--werner-bill` and wrappers still named WernerThinking/WernerSleeping/etc. while rendering the brain — renaming debt, not a visual bug. | Rename when the wrappers are next touched; keep as one batch. |

## Verdicts

### BrainMascot — bring to standard:
1. Rewrite the header docblock to the shipped behaviour (blink + breathing + hover-blink; tilt removed) and delete the dead `perspective`/`.brain-tilt` 3D scaffolding (`:129,133`, `brainMascot.css:19-21`).
2. Decide the fate of the `scene` prop: wire it or delete it and mascotSceneMap with it.
3. Move the blink transition onto the motion scale (150ms or `--motion-base`).
4. Update the false "PenguinMascot NOT re-skinned" claim (`:24-26`).

### BrainMark — waive:
Token-clean, presentational, correct idiom at rail size; the only ask is the
one-line idiom lockup note folded into the README re-author (P2 above).

### BrainPresence — bring to standard:
1. Replace inline `zIndex: 1` with a named ladder layer (`design/zIndex.ts`).
2. Fix the docblock's "pointer tilt" claim.
3. Note the coexistence rule: with BrainPresence always mounted, no route may
   add a second large mascot without violating "never more than one on
   screen" — encode that in the README re-author.

### mascotSceneMap — bring to standard:
1. Rewrite all reason/companion copy in brain voice (kill "Werner").
2. Resolve the dead seam: either a call site passes `scene` or the module
   shrinks to what BrainMascot actually imports.
3. Re-audit POSE_GAPS against the brain pose set (authored head-tilt and
   sleeping poses now exist under `mascot-brain/authored/`).

### werner/animated wrappers — bring to standard:
1. Tokenize the aurora dots in WernerThinking (`#16C2C2` ×4 → `bg-aurora`/`var(--aurora)`).
2. Re-author WernerCaughtAFish's celebrate chrome for the brain — the fish
   and penguin flipper are the wrong mascot's props.
3. Batch the Werner→Brain rename (component names, `--werner-*` vars, CSS
   class prefixes) as one deliberate pass.

### SemanticReactions — waive with one note:
Copy is brain-correct and chrome is semantic; carry it into the batch rename
and re-check its 800–1300ms one-shots against the motion scale then.

### Render sites (NavRail, AppShell, PenguinMascot, Home, Biography, SpeakIndex, CelebrateBurst) — bring to standard:
1. Home.tsx:120 — persistent celebrate → idle or remove (P0).
2. Biography/index.tsx:255 — persistent celebrate → CelebrateBurst one-shot, then idle/none (P0).
3. Unify landing-h1 type (Home:66 text-3xl vs SpeakIndex:124 text-2xl vs Biography:101 text-3xl) and replace `text-[13.5px]`/`text-[15px]` literals with pinned steps.
4. Ratify or evict the header-idle slot (SpeakIndex:122, Biography:99, Home:65) — today these are unratified fifth surfaces under the restraint rule.

### WorkflowStub — bring to standard:
1. Map `text-[11px]`/`text-[15px]`/`text-[13px]` to `text-xxs`/`text-sm`/`text-base`.
2. Decide the empty-mood question: the brand's own restraint rule promises the
   sleepy brain on blank/first-run states; this is the canonical one.

### AIActionFailure — waive:
Contract-correct honest failure: one sentence, framed diagnostic, in-place
retry, `role="alert"`, mascot-free by rule. No action.

### Favicon / marks / index.html — bring to standard:
1. Replace `bg-stone-50 text-stone-900` on `<body>` with token classes (P1).
2. Add og:/twitter: meta wired to the brain social card, published to `public/`.
3. Remove or relocate `public/redesign.html`.
4. Correct PROFILE.md's sun (`#FFD54A`→`#F5DF24`) and space-2 (`#0B1020`→`#0D1019`) values.
5. Consolidate the duplicate `marks/` builders (brain vs penguin) to the brain set.
