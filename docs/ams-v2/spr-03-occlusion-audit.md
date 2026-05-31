# SPR-03 occlusion audit — what stands between the route content and the z-0 `<Scene/>`

**Sprint:** AMS2-SPR-03 (glass surface model + the keystone primitive).
**Status:** audit complete; this is the binding per-surface classification the
apply agents build against. The browser gate (`e2e/ams-shell.spec.ts` anchor
`[scene]`, un-fixme'd by this sprint + the new `glass-surface.spec.ts`) fails
loudly if any later sprint re-introduces an opaque body over the scene.

---

## 0. Method (rigor #3 — pixels + ratios, not vibes; rigor #4 — read the real symbols)

Every surface below was READ on the actual `caffen/AMS2-integration` tree
(off which this branch is cut), not assumed. The full `/` ancestor chain was
traced top-down:

```
AppShell.tsx (src/AppShell.tsx)                         ← frame
  └─ <Scene/>                              z-0, absolute inset-0, pointer-events-none, aria-hidden
  └─ relative column
       └─ Topbar
       └─ <PanelLayout mainSlot={<SceneChrome>{children}</SceneChrome>} />
            └─ SceneChrome (src/shell/SceneChrome.tsx)
                 └─ <div class="flex-1 … bg-glass backdrop-blur-glass">   ← the glass band (SPR-04)
                      └─ children  ==  the route view
                           └─ ResearchWorkstation/index.tsx
                                └─ PanelHost → PanelLayout (again, inner)
                                     └─ StartResearch (idle) | InvestigationCenter (active)
       └─ NavRail (bottom)
```

The four landing route bodies (`Home`, `Speak`, `Library`, `Write`) are the
`children` for their own routes (`/home`, `/speak/:id`, `/library`+`/`-door,
`/write`), each wrapped by the same `SceneChrome` glass band.

"Mountain visible" is proven ONLY by sampling viewport pixels in a
content-free region and asserting NOT `isSolidColor` (variance ≥ 12 OR
distinctColors > 4). "Legible" is proven ONLY by computing text-over-surface
contrast ≥ 4.5:1. Both run in the real-app Playwright gate on `/`.

---

## 1. The frame is NOT the occluder (M5 — record it explicitly)

**`AppShell.tsx:88-106`** — the `[data-akb-shell-frame]` div is **already
`bg-transparent`** (`className="h-screen w-screen bg-transparent text-ink
dark:text-bright overflow-hidden"`). `<Scene/>` is its z-0 first child
(`AppShell.tsx:115`). The nine mounts (Scene, Topbar, PanelLayout, WindowsLayer,
NavRail, PenguinMascot, AdBorderMount, LemonToastViewport, HotkeyHud) do not
paint an opaque sheet over the **working region** (the route body's column).

**BUT the AdBorderMount DOES paint opaque rails — WITH text — in the four edge
insets, and that bears directly on where the scene gate may sample.** Verified
live (vp 1280×720) via the rendered `[data-akb-ad-edge]` rects:
`AdBorder.tsx:151-188` mounts four `<aside class="… bg-ice-1 dark:bg-charcoal-2 …">`
rails inside a `fixed inset-0 z-[150]` container, each rendering an `AdCreative`
whose house fill paints the caption "From the library" + "Explore the antiek
library" (`AdCreative.tsx:62-75`). At the xl/lg tier (the ≥1024px gate viewport)
ALL FOUR are present:

| Edge | Live rect (px @ 1280×720) | Fraction | Paints |
|---|---|---|---|
| top | x∈[0,1280], y∈[0,36] | y 0–0.05 | opaque rail + creative text |
| bottom | x∈[0,1280], y∈[684,720] | y 0.95–1.0 | opaque rail + creative text |
| **left** | x∈[0,96], y∈[36,684] | **x 0–0.075** | opaque rail + creative text (vertically centred ≈ y 360) |
| **right** | x∈[1184,1280], y∈[36,684] | x 0.925–1.0 | opaque rail + creative text |

So the LEFT/RIGHT margins — the very place §3 item 1 and the new specs say the
scene "shows through" — are partly an OPAQUE ad rail painting TEXT, not bare
scene. A scene-visibility region MUST be sampled in the gap BETWEEN the left
rail (ends x=96 ≈ 0.075) and the centred content column (starts x=256 ≈ 0.20),
below the SceneChrome action bar (ends y≈0.214) and above the bottom rail
(starts y≈0.95). The headline gate (`glass-surface.spec.ts`) samples exactly
that gap (fractions x 0.085–0.18, y 0.30–0.78 → px x∈[109,231], y∈[216,562]) and
proves it NON-VACUOUS with a live negative control (hide the z-0 scene → the band
collapses to one flat colour; variance falls from ≈260 to 0). An earlier cut
sampled x 0.02–0.16, which straddled the opaque left rail + its creative text and
so reported variance ≈933 with the scene shown AND ≈680 with it HIDDEN — a false
green. The corrected region + the negative control close that hole.

**DECISION: do NOT touch `AppShell.tsx`** (the AdBorderMount is correct chrome —
the fix is choosing the gate region OFF the rails, not changing the frame).
`AppShell.spr06.test.tsx` and `AppShell.hotkeys.test.tsx` pass automatically as
long as the frame's four `--akb-border-inset-*` paddings + `box-sizing:
border-box` + NavRail-after-region ordering are untouched. The occlusion of the
route content is entirely in the ROUTE BODIES; the ad rails occlude only their
own reserved inset band (by design, M6 of SPR-07).

---

## 2. The intermediate chain paints NO opaque sheet (confirm (b))

| File:line | Surface | Paints? | Verdict |
|---|---|---|---|
| `src/workspace/PanelLayout.tsx:128` | outer/inner layout root | `bg-transparent` (SPR-04 comment in code) | **NOT an occluder.** Scene shows through. |
| `src/workspace/PanelLayout.tsx:142-144` | `<main>` + `<div absolute inset-0 overflow-auto>` mainSlot wrapper | no bg | **NOT an occluder.** |
| `src/workspace/PanelLayout.tsx:131,159,185` | left/right/bottom DOCKS | `bg-ice-1 dark:bg-charcoal-1` | **CHROME, keep opaque.** A dock is a panel container, not a landing surface; its width animates to 0 when empty. Out of this sprint's scope (those are workspace chrome, not route bodies) and legible by design. |
| `src/workspace/PanelLayout.tsx:93` | tier-`sm` "use a larger screen" splash | `bg-ice-2 dark:bg-space-2` | **CHROME, keep opaque.** Only renders below 768px where the workspace is explicitly unsupported; never on the ≥1024px gate viewport. Out of scope. |
| `src/shell/SceneChrome.tsx:179` | action-bar / tabs strip | `bg-ice-1 dark:bg-charcoal-2` | **CHROME, keep opaque.** A 40px control strip, not a content body. Legible by design; leaving it opaque is correct. |
| `src/shell/SceneChrome.tsx:267` | the scene band wrapping `children` | **`bg-glass backdrop-blur-glass`** (SPR-04 already glassed) | **ALREADY GLASS.** This is the band the scene shows through. **It does NOT guarantee AA over a busy scene** (tokens.css L58-66 / tokens.ts `glass`) — the route body inside it must add the scrim. SceneChrome glasses the *band*; the route body owns the *scrim*. |
| `src/workspace/PanelHost.tsx:79` | `<PanelLayout mainSlot={children}>` | no bg | **NOT an occluder.** Pure pass-through. |

So `SceneChrome`, `PanelHost`, and `PanelLayout` do NOT paint opaque over the
scene (the expected result). The single glass band at `SceneChrome.tsx:267` is
the seam the scene shows through. **The opacity that occludes the mountain is
painted by the ROUTE BODIES nested inside that band** — they each set their own
`bg-ice-*`/`bg-space-*`/`bg-charcoal-*` full-bleed background, which sits ON TOP
of the glass band and re-occludes the scene.

---

## 3. The occluding surfaces — per-surface classification + treatment

Classification key:
- **landing-glass** → a LANDING-like surface (orientation / composer / shelf /
  warm front door). Glass the content container (consume `GlassSurface`),
  scrim the body text so it clears AA over the moving scene, let the scene show
  through the margins/gaps. The scene must be visible here.
- **dense-legible-keep-opaque** → a dense, in-window working surface where
  transparency would break readability (rigor #1). Keep `GlassSurface
  variant="solid"` (the opaque-in-window fallback, same hue, no colour jump).
  The scene does NOT show through these; they read as solid cards.

| # | File:line | Opaque class today | Classification | Treatment (apply phase) |
|---|---|---|---|---|
| 1 | `src/modes/ResearchWorkstation/StartResearch.tsx:423-431` (idle `/` home root) | **none** — the root `<div>` is background-free; the bare `h1` (L432) + intro `<p>` (L435) sit DIRECTLY over the scene | **landing-glass** | The root is already background-free, so the scene shows through the margins around the centred `max-w-3xl` column — this is exactly why the `[scene]` anchor can sample a content-free margin. The LEGIBILITY RISK is the bare heading/intro text over the moving scene. Apply phase: wrap the heading+intro (and the composer/pills/log column) in `GlassSurface variant="glass"` so the scrim carries those texts above 4.5:1. The composer/pills cards already have their own `bg-ice-0` — those become `GlassSurface` too (or keep their card bg as the scrim band). **Do NOT add a full-bleed opaque bg to the root** — that would re-occlude the scene. |
| 2 | `src/modes/Home/Home.tsx:55` | `bg-ice-2 dark:bg-space-2` (full-bleed `h-full w-full overflow-y-auto`) | **landing-glass** | The warm branded front door. Apply phase: drop the full-bleed `bg-ice-2 dark:bg-space-2` so the scene shows through, and wrap the centred `max-w-3xl` content (`L56`) in `GlassSurface variant="glass"`. The four door cards (`L85-91`, `bg-ice-0 dark:bg-charcoal-2`) and the biographies panel (`L111`) become their own glass/solid cards or keep their card bg as the scrim. |
| 3 | `src/modes/Speak/index.tsx:229` | `bg-ice-0 dark:bg-charcoal-2` (full-bleed `h-full overflow-y-auto`) | **landing-glass** | The Speak project page is a warm, focused single-column landing (invite link + arriving voices + corroboration + assembling story), NOT a dense IDE. Apply phase: drop the full-bleed bg so the scene shows through the margins around the `max-w-2xl` column (`L230`), wrap that column in `GlassSurface variant="glass"`. The inner section cards (e.g. `L277` invite section `bg-ice-0 dark:bg-charcoal-1`) keep their card backing as the scrim band for their own body text. |
| 4 | `src/modes/Library/index.tsx:177` | `bg-ice-0 dark:bg-charcoal-2` on `<main>` — **EXCEPT** an `inWindow` branch that already uses `bg-transparent` (`L177`, gated on `useInWindow()`) | **landing-glass** | The Read door shelf/grid. **PRESERVE THE `inWindow` VARIANT** (it already drops the opaque bg to let the SPR-09 window glass show through). For the FULL-PAGE branch (`!inWindow`), apply phase: replace `bg-ice-0 dark:bg-charcoal-2` with the `GlassSurface variant="glass"` treatment so the full-page Library at `/library` (and as the Read door) reveals the scene. The shelf header (`L180`) + book cards keep their own legible backing. The `inWindow` ternary stays: `inWindow ? "bg-transparent" : <glass treatment>`. |
| 5 | `src/modes/Write/WriteHome.tsx:149` (Home / no-piece branch) | **none on the root** — `mx-auto h-full max-w-3xl overflow-y-auto`; the start-a-piece panel (`L160`) is `bg-ice-0 dark:bg-charcoal-2`, the pieces list rows (`L220`) `bg-ice-0 dark:bg-charcoal-2` | **landing-glass** | The Write door (no piece) is a landing: start a piece / brainstorm / pick a piece. The root is already background-free → scene shows through the margins around the `max-w-3xl` column. Apply phase: wrap the column / the start-a-piece panel in `GlassSurface variant="glass"`; keep the inner panel/rows as their scrim band. |
| 6 | `src/modes/Write/WriteHome.tsx:238` (piece-open branch) | `bg-ice-1 dark:bg-charcoal-2` (`flex h-full min-h-0`) — outline + repository working surface | **dense-legible-keep-opaque** | A piece open = the outline editor + tap-to-add block repository = a DENSE working surface (the same family as the Research IDE). Apply phase: this becomes `GlassSurface variant="solid"` (opaque-in-window, same hue, no colour jump). The scene does NOT show through the open-piece editor. Rationale = rigor #1 below. |

### The dense `/inv/:id` IDE — stays opaque-in-window (confirm (c), rigor #1 honesty rejection)

| File:line | Surface | Classification | Why it stays opaque |
|---|---|---|---|
| `src/modes/ResearchWorkstation/index.tsx:152-187` | `InvestigationCenter` — ThinkingStream + NotesPanel + DistillView, the ACTIVE `/inv/:id` DENSE IDE | **dense-legible-keep-opaque** | This is the surface M3 protects. `NotesPanel` header is `bg-ice-1 dark:bg-charcoal-2` (`index.tsx:225`); the aside is a `w-[320px]` notes column with a `border-l`. It is a high-density, long-session reading/working surface (live thinking stream, scored notes, distilled insights, cited prose). Translucency here would put body text over a moving mountainscape across a dense layout — exactly the readability failure M3 exists to prevent. **A glass surface that fails AA is worse than an opaque one that reads (rigor #1).** **AUDIT GROUND-TRUTH CORRECTION (apply phase, recorded so the committed decision matches shipped code):** "untouched-opaque" was NOT sufficient. On the real tree only the HEADER strips inside this view carry an opaque bg (`ThinkingStream.tsx:239` `bg-ice-1`, the Notes header `index.tsx:225`, `MasterMdViewer.tsx:272`); the dense BODY areas (ThinkingStream body, DistillView, NotesPanel rows) are background-FREE. Left untouched, those bodies would render directly over the translucent `SceneChrome` glass band (`SceneChrome.tsx:267`) — i.e. dense body text over the moving scene, the exact M3 failure. So the implementation does NOT leave it untouched: it wraps the whole dense centre in `GlassSurface variant="solid"` (`index.tsx:173-187` — `bg-glass-solid`, same hue, alpha 1, NO backdrop-filter, NO scrim), the opaque-in-window fallback, which restores the guaranteed opaque backing the dense text needs. The scene shows through the LANDING surfaces and the shell margins, not the dense IDE. The `/` idle home (StartResearch, item 1) is the LANDING counterpart of this route and IS glassed — that resolves the M3 tension: idle `/` = landing-glass, active `/inv/:id` = dense-opaque (now via `variant="solid"`, not by accident of an opaque body). |

---

## 4. Steelman: "leave the route bodies opaque" (rigor #2 — fairness, recorded)

The strongest case for leaving every route body opaque, stated fairly:

> The opaque `bg-ice-*`/`bg-space-*` bodies guaranteed readable text. They put a
> known, flat, high-contrast surface behind every word — no scene-bleed could
> ever drop a heading below the WCAG floor, in any theme, behind any frame of a
> moving procedural mountainscape. v1 shipped INVISIBLE precisely because nobody
> proved the scene was visible; but the *symmetric* failure — glassing a surface
> whose text then fails AA on a busy frame — is a worse regression, because it
> ships looking intentional while quietly failing accessibility. The safest move
> is to leave the bodies opaque and let the scene live only in the shell chrome.

**Why we override it (without dismissing it):** the resolution is NOT "make
everything transparent." It is **translucent where text survives, solid where it
does not, never a void.** The audit splits surfaces into landing-glass vs
dense-opaque exactly so the steelman's concern is honored: dense text surfaces
(the `/inv/:id` IDE, the open Write piece) STAY solid; only landing surfaces go
glass, and they go glass through a single primitive (`GlassSurface`) that OWNS
the scrim math in one place and DEGRADES to the identical solid fallback under
reduced-motion / no-scene. The steelman's "no scene-bleed can drop a heading
below the floor" is preserved by the scrim contract (§5) + the browser contrast
gate, not abandoned. The steelman correctly rejects naive transparency; it does
not reject scrimmed glass that is pixel-proven to clear AA.

---

## 5. The scrim contract the apply agents inherit (defensibility #5)

`GlassSurface variant="glass"` guarantees body text clears WCAG AA 4.5:1 over
ANY frame of the moving scene, because the primitive owns the scrim in one
place. The contract (the exact numbers proven in `GlassSurface.test.tsx`):

- Glass fill is the token `--glass-bg` (day `rgba(251,252,253,0.72)`, night
  `rgba(27,32,42,0.66)`) — consumed via the `bg-glass` Tailwind class, never
  redefined (SPR-09 owns the token).
- The scrim is an additional solid-fallback layer (`--glass-bg-solid`) the
  primitive composites BEHIND the content at a fixed opacity, so the *effective*
  text background is at least `SCRIM_MIN_OPACITY` of the solid hue regardless of
  the scene. With the worst-case scene backdrop (black behind day glass, white
  behind night glass), ink-on-day-glass and bright-on-night-glass both clear
  4.5:1 — the scrim only adds margin to the already-passing solid contrast.
- **Scrim covers the FULL scroll content, not just the visible client box.**
  Several landings (`Home`, `Speak`, `Library`, `Write` home) put
  `overflow-y-auto` ON the GlassSurface, so the scrim cannot be a bare
  `absolute inset-0` on the scroll container (that sizes to the client box and
  below-the-fold text would lose the scrim, eroding night 5.87:1 → bare-glass
  4.66:1 on exactly the long pages). The primitive therefore nests the scrim +
  content in an inner `relative min-h-full` flow div whose height tracks the full
  `scrollHeight`, so the scrim backs every line, above and below the fold;
  `min-h-full` is a no-op for indefinite-height (non-scroll) consumers, so it
  never stretches a fixed-height layout (`GlassSurface.tsx` glass branch).
- Under `prefers-reduced-motion: reduce` OR `sceneAbsent` (offline / no Krea key
  / over-budget — no moving scene behind), the glass variant renders the SOLID
  fallback (`bg-glass-solid`, no `backdrop-filter`), identical to
  `variant="solid"`, so the contrast guarantee is IDENTICAL and every screen
  stays complete + legible with zero scene behind it (M4 / RULE 3).

The browser gate (`glass-surface.spec.ts`) proves on the real `/` route that
(a) a content-free scene region (the gap between the left ad rail and the content
column — §1) is NOT solid (mountain visible), (b) that SAME region is
NON-VACUOUS — a live negative control hides the z-0 scene canvas and asserts the
band collapses to one flat colour, proving the variance in (a) comes from the
MOUNTAIN and not from chrome/text leaking into the band — and (c) the glass-backed
body text clears `assertContrast ≥ 4.5`. If a later sprint repaints an opaque body
over the scene, the scene assertion goes red; if a later sprint moves the gate
region back onto chrome/text, the negative control goes red.

`assertContrast` (e2e/_ams/visible.ts) proves (b) OVER THE SCENE, not over the
glass hue treated as opaque: when the resolved background is translucent it
reads the real computed fill alpha + the `[data-glass-scrim]` colour/opacity and
alpha-composites `fill over [scrim over scene]` against BOTH worst-case scene
extremes (pure black + pure white), asserting the WORSE of the two clears 4.5
(day-glass-over-black ≈ 10.55:1; night-glass-over-white ≈ 5.87:1 — the same
bounds `GlassSurface.test.tsx` proves, now computed from live token values). So
a regression to `--glass-bg` alpha or `SCRIM_MIN_OPACITY` that erodes over-scene
contrast reddens THIS gate, not only the unit math.

---

## 6. Summary of edits the apply phase will make (this keystone makes NONE of them)

- Items 1-5 (landing-glass): drop full-bleed opaque bg, wrap content column in
  `GlassSurface variant="glass"`. Preserve Library's `inWindow → bg-transparent`
  branch.
- Item 6 + `/inv/:id` IDE (dense-legible): `GlassSurface variant="solid"` —
  explicitly NOT transparent. NB the apply phase found the dense bodies
  background-FREE (only the header strips were opaque), so "leave opaque" was
  NOT viable; the dense centre is positively re-backed with `variant="solid"`
  (see the §3 dense-IDE row's audit ground-truth correction).
- Tokens (`tokens.css`/`tokens.ts`), `scene/`, `components/windows/`,
  `AppShell.tsx`: UNTOUCHED.

This keystone delivers only the audit, the `GlassSurface` primitive, and its
test. The apply agents consume `GlassSurface` per this table.
