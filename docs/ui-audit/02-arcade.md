# 02 — The Arcade

Scope: everything under `apps/reading/src/arcade/` (engine, cartridges, factory, flag), plus the surfaces that make it a product experience: the wait-arcade host in `modes/DeepResearchWorkspace/`, the key art in `brand/werner/arcade/`, and how the whole thing sits inside the shell. Audited against `src/design/DESIGN_LANGUAGE.md`, `src/design/FEEL_CONTRACT.md`, `tokens.ts`, `elevation.ts`, and `motion.css` first; general craftsmanship second.

Verification run: `npm run lint:tokens` → OK (no new hardcoded hex; zero hex literals anywhere in `src/arcade/`). `npm run lint:type` → OK (chrome ceiling only; canvas `fillText` sizes are not covered by that gate). Both key-art webp files exist at the documented sizes and were visually inspected.

## Surfaces

### Arcade engine core
`src/arcade/engine/loop.ts:52`, `rng.ts:5`, `types.ts:48`, `demoCartridge.ts:7`, `index.ts:1`
A fixed-timestep (1/60, max 5 substeps, 50 ms clamp) rAF loop with an injectable host, a seeded Mulberry32 RNG, and a `Cartridge` plugin contract (`init → (update/render)* → teardown`, optional `getScore`/`isGameOver`). Pure logic is cleanly separated from canvas presentation. The loop pauses when the document is hidden and has a genuine reduced-motion path (one static frame at start, `stepOnce` per input). This is the strongest code in scope — deterministic, testable, honestly documented.

### ArcadeMount (canvas host component)
`src/arcade/engine/ArcadeMount.tsx:22`
Mounts a cartridge on a `<canvas>`: wires keyboard/pointer listeners, pointer capture, seeded RNG, best-score refs, and the loop; tears everything down on unmount. Ships accessibility scaffolding (`role="application"`, `tabIndex=0`, `aria-label` from `cartridge.meta.title`, an sr-only instructions block). Inline style sets fixed pixel width/height, `borderRadius: 8`, and `background: var(--card-soft)`.

### Ice Fishing cartridge
`src/arcade/games/ice-fishing/iceFishingCartridge.ts:10`, logic in `logic.ts:139`
Club-Penguin-inspired drop/reel catch loop. Pure immutable state machine (`ready → playing → gameover`) with a reduced-motion simplified path (no motion, click awards points). Render paints a fixed **day** scene (ice `surface.day[4]`, water `surface.day[6]`, ink hole, sun line/hook, aurora/glow/emperor fish) and a `12px system-ui` HUD.

### Paperclip Zombies cartridge
`src/arcade/games/zombies/zombiesCartridge.ts:6`, logic in `logic.ts:100`, presentation in `zombiesVisuals.ts:49`
BO1-zombies-inspired fort defence: endless waves, click-to-fire, Escape-to-exit, `ready → playing → gameover | exited`. Presentation is a fixed **night** scene — layered field, evidence traces, fort with sun diamond, paperclip sprites with HP pips, mono HUD band and status plate with ALL-CAPS phase copy (`OPEN THE NIGHT FILE · CLICK OR ENTER`), plus a compact (<240 px) variant at 6 px. The most visually considered canvas in scope.

### Cartridge factory + genre metadata
`src/arcade/cartridgeFactory.ts:15`, `src/arcade/engine/types.ts:24-30`
`createArcadeCartridge("ice-fishing" | "zombies", { reducedMotion })` — the single entry point — plus `progressCartridge`, a headless score/wave progression harness for tests. `CartridgeMeta` carries `title`, `blurb`, and a `style` tag typed as `"club-penguin" | "zombies-arcade" | "demo"`.

### Wait-arcade experience (the product surface)
`src/modes/DeepResearchWorkspace/ResearchWaitArcade.tsx:54`, `ResearchWaitArcadeGame.tsx:10`, `ResearchWaitArcade.css:1`, `researchWaitArcadePolicy.ts:20`
An `<aside>` under the research monitor: a status rail (sun diamond pulse + evidence trace + "N researches still running"), then — after an 8 s timer — an offer drawer with a two-cartridge radio chooser (key art + serif title + description) and a primary `LemonButton` ("Play while waiting"). Opt-in lazily loads `ResearchWaitArcadeGame`, which builds the cartridge through the factory and mounts it at 480×300. Escape exits with focus restore; the station-instrument lens is suspended during play. Policy (`deriveResearchWaitArcadeMode`) gates on flag, snapshot authority, active research count, terminal state, reduced motion, timer, and opt-in.

### Shell integration
`src/modes/DeepResearchWorkspace/index.tsx:392-458`, `src/arcade/waitArcadeFlag.ts:6`
`ResearchWaitArcadeGate` renders the lazy arcade only when eligible (flag `VITE_WERNER_RESEARCH_WAIT_ARCADE=1`, active research, non-terminal), keyed by `sessionId:generation`, returning focus to the monitor heading on unmount. Disabled sessions never even load the chunk. Sits as a full-width band between the monitor header and the research-card grid.

### Key art
`src/brand/werner/arcade/ice-fishing-station-key-art-v1.webp`, `paperclip-archive-key-art-v1.webp`, `README.md:1`
Two 1200×800 webp illustrations (285 KB + 180 KB), gpt-image-2-generated, documented with prompts, SHA-256s, and production transforms. Visually inspected: a coherent day/night pair — glacier blue, paper white, ink, brass, muted coral, screen-print texture; the ice-fishing art is a calm day scene (rod, hole, observatory), the paperclip art a moody night archive under paperclip siege. Deliberately no mascot in either. Displayed at `aspect-ratio: 3/2`, `object-fit: cover`, `alt=""` in the chooser.

## Findings

| Severity | Location | Issue | Fix direction |
|---|---|---|---|
| P0 | `researchWaitArcadePolicy.ts:23-31` vs `loop.ts:115-122`, `ArcadeMount.tsx:76,97,106`, `logic.ts:164-198,234-237` (ice), `logic.ts:141-143,172-177` (zombies) | Reduced-motion users get **nothing**: policy returns `"hidden"` when `reducedMotion` is set, yet the engine, both cartridges, and `ArcadeMount` implement a complete reduced-motion play path (static frame, click-to-step, simplified scoring). That path is dead code in the only real host, and the feature's function is silently withdrawn from exactly the users motion.css promises "function is never lost". | Map reduced motion to `"offer"` with reduced cartridges instead of `"hidden"`; the static-frame + step-on-input experience already exists and is tested. |
| P1 | `iceFishingCartridge.ts:92` | HUD font `"12px system-ui, sans-serif"` bypasses the canonical type families (`type.sans` Inter / `type.mono` JetBrains Mono). The sibling cartridge uses `${type.mono}`. | Use `` `12px ${type.mono}` `` (or a shared HUD type helper). |
| P1 | `zombiesVisuals.ts:211,222,234,255`; `iceFishingCartridge.ts:92` | Canvas type sizes are off-scale and mutually inconsistent: zombies uses 6/9/10 px mono; ice fishing uses 12 px sans. The token scale floors at `xxs` 10 px — the 6 px compact HUD is illegible by any standard. | Floor canvas text at 10 px; share one HUD typography helper across cartridges; drop or redesign the 6 px compact band. |
| P1 | `zombiesVisuals.ts:222-224,233-235` | HUD labels (`NIGHT FILE`, `FORT`) render `surface.night[7]` moonlight `#6B7585` on `night[4]` charcoal-2 `#1B202A` ≈ 3.4:1 — below the 4.5:1 floor the token layer commits to for text. | Use `night[8]`/`night[9]` for HUD text; keep moonlight for non-text rules. |
| P1 | `iceFishingCartridge.ts:17,59-98` vs `zombiesVisuals.ts:72-255` | Sibling cartridges pin **opposite fixed modes**: ice fishing always paints the day ramp (`aliasFor("day")`); zombies always paints the night ramp. Neither follows app theme, and no exemption (cf. `ELEVATION_EXEMPT_SURFACES`) documents this. In day mode the zombies canvas is a void-black box; in night mode ice fishing is a white slab. | Pass mode into cartridges and pick ramps via `aliasFor(mode)`, or add a documented cartridge-scene exemption to the design docs. |
| P1 | `zombiesVisuals.ts:15-27` vs `iceFishingCartridge.ts:96-98` | HUD voice split between siblings: zombies uses ALL-CAPS mono cabinet copy (`OPEN THE NIGHT FILE · CLICK OR ENTER`); ice fishing uses sentence case (`Click / Space to fish`). | One copy convention (case, punctuation, control hints) shared by both cartridges. |
| P1 | `ArcadeMount.tsx:179` | Inline `borderRadius: 8` — off the radius scale (`sm 4 / hog 6 / hog-lg 10`); also mismatches the 6 px `--radius` of the enclosing `.research-wait-arcade__canvas-shell` (`ResearchWaitArcade.css:146`), so canvas corners and shell corners disagree. | `var(--radius)` or token-driven value matching the shell. |
| P1 | `ArcadeMount.tsx:173-181` | Fixed pixel `width`/`height` in style + `maxWidth: 100%`: when the container is narrower than 480 px the canvas compresses horizontally but keeps its fixed height — aspect distortion of the whole game. | `height: auto` + `aspect-ratio`, or size via CSS with the drawing buffer scaled. |
| P1 | `ArcadeMount.tsx:184-186` | The sr-only instructions block hardcodes **both** games' controls regardless of the mounted cartridge ("Arrow keys control Ice Fishing. Pointer or keyboard controls Paperclip Zombies."), and promises Escape behaviour the shell intercepts (see P2 below). Screen-reader users get wrong instructions half the time. | Derive instructions per cartridge (add an `instructions` field to `CartridgeMeta`). |
| P1 | `ResearchWaitArcade.tsx:26-44` vs `iceFishingCartridge.ts:21-25`, `zombiesCartridge.ts:16-20` | Chooser title/description are duplicated in `ARCADE_CHOICES` instead of consumed from `CartridgeMeta`; the zombies copy has already drifted ("Defend the archive while research keeps running." vs meta blurb "Defend the fort while deep research runs."). | Single source of truth: read title/blurb from the cartridge meta. |
| P1 | `ResearchWaitArcade.css:73-135` | Cartridge cards have no hover-lift and no transition: the FEEL contract names hover-lift on cards as a primitive (`motion.ts:48` `cardLift`), and selection changes snap instantly with no motion-token transition. | Add `cardLift`/`press` transitions via the motion scale to the cartridge cards and choice mark. |
| P1 | `ResearchWaitArcade.tsx:158` | `text-[11px]` arbitrary value — off the 10/12/14 px scale. Matches the host's existing `[11px]` drift (`index.tsx:361,387`), so this is a host-wide pattern, but still off-scale. | `text-xxs` (10 px) or `text-xs` (12 px); sweep the host's `[11px]` together. |
| P2 | `cartridgeFactory.ts:1-5` | Header comment cites "ArcadeCabinet and LoadingGameHost" as the two consumers — neither exists in the tree; the only host is `ResearchWaitArcade`. Stale architecture doc in the file's own contract comment. | Correct the comment (or build the cabinet). |
| P2 | `types.ts:29` | Genre tags `"club-penguin" | "zombies-arcade"` bake borrowed-franchise names into the type contract; §5.6 keeps borrowed voice/mascot out of the product. | Neutral genre tags (e.g. `"fishing" | "defense"`). |
| P2 | `zombiesCartridge.ts:38-39`, `zombiesVisuals.ts:19` vs `ResearchWaitArcade.tsx:147-153` | Two exit authorities: the cartridge's Escape→`exited` phase (with `SHIFT CLOSED` copy) is unreachable in the shell because the aside's capture handler intercepts Escape first and stops propagation. | One owner of Escape; either delete the cartridge phase or let it render before the shell exits. |
| P2 | `ResearchWaitArcade.tsx:254-272` vs `workspace/usePrefersReducedMotion.ts:18` | Local `useReducedMotionPreference` duplicates the shared hook the gate already uses (`index.tsx:438`) — and the gate computes reduced motion but never passes it down, so the component re-subscribes to the same media query. | Import the shared hook (or pass the gate's value as a prop). |
| P2 | `ResearchWaitArcade.tsx:241`, `index.tsx:451` | `Suspense fallback={null}` at both lazy boundaries: blank canvas shell while the game chunk loads; no skeleton, no error boundary if the chunk fails. | Skeleton block at 3:2 in the canvas shell + an error state. |
| P2 | `ArcadeMount.tsx:163-182` vs `ResearchWaitArcade.css:151-155` | The canvas focus ring lives only in the wait-arcade CSS, scoped to `.research-wait-arcade canvas`. `ArcadeMount` is exported as public engine API (`engine/index.ts:18`) — any other mount gets no visible focus ring. | Co-locate a default focus style with `ArcadeMount`. |
| P2 | `ResearchWaitArcade.tsx:187-192` | Key art rendered `alt=""` + `aria-hidden`: the art is the primary genre signal in the chooser but is invisible to assistive tech; only the text label carries it. Defensible as decorative, but undocumented. | Give the images real alt text, or record the decorative decision in the key-art README. |
| P2 | `brand/werner/arcade/README.md:10,38-40,49-51` | Key art is a second illustration dialect: "flat editorial with screen-print texture" via gpt-image-2, while the shipped visual language elsewhere is thick-outline pastel Krea art (cf. `linkMonster` tokens' Krea-profiled art direction). The pair is handsome and internally coherent, but it is not the house style. | Re-profile future key art through the house Krea style; note the dialect choice in DESIGN_LANGUAGE if kept. |
| P2 | `ResearchWaitArcade.css:5,145` | Mixed edge widths inside one component: the aside uses the brand `var(--edge)` 2.5 px border while the canvas shell inside uses a 1 px border — the chunky-edge brand mark thins out at the one place the game lives. | `var(--edge)` on the canvas shell, or document hairline-inset as a rule. |
| P2 | `ResearchWaitArcade.tsx:127,164-220` | The offer drawer appears abruptly after the 8 s timer — no enter motion, though `motion.ts:62` `enter` exists for arriving elements. | Apply the enter transition to the drawer. |

## Verdicts

### Arcade engine core — bring to standard:
1. Fix the stale consumer comment in `cartridgeFactory.ts:1-5` (P2 #13).
2. Rename franchise genre tags in `types.ts:29` (P2 #14).
3. Otherwise hold — loop, RNG, and contract are the model for the rest of the scope.

### ArcadeMount — bring to standard:
1. Replace `borderRadius: 8` with the radius token and match the shell (P1 #7).
2. Fix aspect distortion with `height: auto` + `aspect-ratio` (P1 #8).
3. Per-cartridge sr-only instructions from `CartridgeMeta` (P1 #9).
4. Co-locate a default focus ring with the component (P2 #18).

### Ice Fishing cartridge — bring to standard:
1. Token the HUD font (`type.mono`) and align size with the shared HUD helper (P1 #1, #2).
2. Resolve mode-blindness: `aliasFor(mode)` or a documented scene exemption (P1 #4).
3. Adopt the shared HUD copy convention (P1 #6).

### Paperclip Zombies cartridge — bring to standard:
1. Raise HUD text off `moonlight` to clear 4.5:1 (P1 #3).
2. Floor compact HUD at 10 px — kill the 6 px band (P1 #2).
3. Resolve the dead Escape/`exited` path with the shell (P2 #15).
4. Same mode-blindness and copy-convention fixes as ice fishing (P1 #4, #6).

### Wait-arcade experience — bring to standard:
1. Stop hiding from reduced-motion users; offer the reduced cartridges (P0 #1).
2. Consume `CartridgeMeta` for chooser copy — kill the drifted duplicates (P1 #10).
3. Add hover-lift/press transitions to cartridge cards (P1 #11).
4. Replace `text-[11px]` with scale values (P1 #12).
5. Loading skeleton + error state for the lazy game; enter motion for the drawer; share the reduced-motion hook (P2 #16, #17, #22).
6. Reconcile the 1 px canvas-shell border with the 2.5 px brand edge (P2 #21).

### Shell integration — waive:
The gate is disciplined (no chunk load when ineligible, episode-keyed reset, focus restore); its only blemishes (`text-[11px]`, reduced-motion not threaded through) are counted against the wait-arcade surface above.

### Key art — bring to standard:
1. Decide and document the illustration dialect vs the house thick-outline style (P2 #20).
2. Alt text or a recorded decorative decision (P2 #19).
