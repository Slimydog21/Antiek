# Scene mood-matrix audit — the before/after photo, every cell

**Sprint:** ALC SPR-05 (procedural scene beauty) · **Milestone:** M1
**Tree:** worktree `caffen/ALC-SPR-05` off integration `3666e266`
**Method:** DETERMINISTIC static-render harness (no Storybook scene story — it is
filterShot-EXCLUDED from the visual rail, `lostpixel.config.ts:51-54`). The
harness renders each cell's atmosphere (`ProceduralSky`) + depth planes
(`Mountainscape`) through the memoized/seeded path and serialises the DOM to
`src/scene/__matrix__/artifacts/<cell>.html` — a byte-stable, diffable artifact
per cell (the markup-level "screenshot": exact gradient stops, glow, star
placement, peak fills, plane recession). Harness: `src/scene/__matrix__/snapshot-matrix.test.tsx`.

## The full state space (DERIVED from mood.ts, not assumed)

`mood.ts` declares `DayPart = dawn | day | dusk | night` (4) × `Weather = clear | snow`
(2) = **8 TYPE cells**. `moodKey(mood) = ` `` `${dayPart}|${weather}` `` (`mood.ts:75`).
The harness enumerates ALL 8 (no sampling) and asserts the set is exactly:
`dawn|clear, dawn|snow, day|clear, day|snow, dusk|clear, dusk|snow, night|clear, night|snow`
(`snapshot-matrix.test.tsx` — "enumerates the FULL 8-cell state space").

### What actually EMITS each cell (the activation reality)

- `moodFromTheme()` (`mood.ts:53`) emits ONLY `day|snow` (OS light) and
  `night|snow` (OS dark). Weather is hardcoded `snow`. So **2 of 8 cells are
  what any user has ever seen.**
- SPR-06 (parallel) adds a CONTINUOUS phase scalar that DRIFTS the visual light
  through `dawn → day → dusk → night`. The discrete mood stays day/night for the
  Krea fetch (unchanged — SPR-05 does not touch the fetch path). So **`dawn|snow`
  + `dusk|snow` are the visual DRIFT ANCHORS SPR-06 interpolates between** — they
  must be designed to excellence even though no source emits them discretely today.
- The 4 `clear-*` cells have **NO activating source** (weather is hardcoded snow,
  and there is no clear-weather emitter). They render GRACEFULLY (full atmosphere,
  no crash) but receive **no pixel-perfection investment** — that would be growing
  the matrix (a NEW weather dimension), which is out of scope.

### The honest split (binding for this audit)

| Split | Cells | SPR-05 investment |
|---|---|---|
| **EMITTED today** (what users see) | `day\|snow`, `night\|snow` | designed to excellence |
| **DRIFT ANCHORS** (SPR-06 lights up) | `dawn\|snow`, `dusk\|snow` | designed to excellence |
| **RESERVED / graceful-only** | `dawn\|clear`, `day\|clear`, `dusk\|clear`, `night\|clear` | graceful render, no crash, NO pixel investment |

Weather (clear vs snow) does NOT branch the SKY atmosphere — the sky-LAYER tokens
(gradient stops / glow / haze / star colour) are a function of `dayPart` only
(`atmosphereFor(dayPart)`, `palette.ts:87`). So a `*-clear` cell shares the
IDENTICAL sky-layer token set with its `*-snow` sibling. **The whole CELL is not
identical, though:** the seeded GEOMETRY differs, because the field seed is
`fieldSeed(moodKey(mood))` and `moodKey = ${dayPart}|${weather}` (`mood.ts:75`)
— weather is IN the seed. So `day|clear` and `day|snow` draw the SAME sky colours
but a DIFFERENT ridge silhouette, a different star placement (at night/dusk), and
different plane geometry, plus a lighter/absent snow flurry (`moodAlpha`,
`palette.ts:53`). This is HONEST and correct: the sky palette is designed per
dayPart anchor; the weather axis varies geometry/particles but stays reserved for
pixel investment.

## The matrix — every cell, before → after, with verdict

"Before" = SPR-04 baseline (`ProceduralSky` = a single 3-stop Tailwind gradient
class `bg-gradient-to-b from-X via-Y to-Z`, branching ONLY day vs night; no glow,
no stars, no aerial haze; no foreground depth planes). "After" = SPR-05 (layered
atmosphere per dayPart anchor + seeded stars + aerial haze + a 3-plane
`Mountainscape`). Evidence column cites the deterministic artifact.

| Cell | BEFORE (SPR-04) | AFTER (SPR-05) | Verdict | Evidence |
|---|---|---|---|---|
| `day\|snow` | bright ice 3-stop gradient, no glow/haze, flat day peaks | 4-stop ice ramp + soft bright horizon glow + far-band aerial haze + 3 foreground depth planes | **DESIGNED** (emitted) | `artifacts/day_snow.html` · sky `scene-sky-day-0`, glow, haze, 3 planes |
| `night\|snow` | deep-space 3-stop gradient, no stars | 4-stop space ramp + cold faint moonlit horizon glow + **48 seeded stars** + aerial haze + 3 depth planes | **DESIGNED** (emitted) | `artifacts/night_snow.html` · 48 `<circle>` stars, byte-stable |
| `dawn\|snow` | mapped to the DAY branch (indistinguishable from day) | distinct cool pre-light ramp warming to a weathered-straw skyline glow; cool glacial peaks; no stars | **DESIGNED** (drift anchor) | `artifacts/dawn_snow.html` · sky `scene-sky-dawn-0`, distinct from day |
| `dusk\|snow` | mapped to the NIGHT branch (indistinguishable from night) | distinct space ramp cooling down with a warm straw horizon (mirror of dawn) + **48 first stars** + twilight peaks | **DESIGNED** (drift anchor) | `artifacts/dusk_snow.html` · sky `scene-sky-dusk-0`, 48 stars |
| `day\|clear` | day gradient (weather had no visual effect) | SAME sky-layer tokens as `day\|snow` (sky is dayPart-only); DIFFERENT seeded ridge/plane geometry; lighter/absent flurry | **GRACEFUL** (reserved) | `artifacts/day_clear.html` · renders, no crash |
| `night\|clear` | night gradient | SAME night sky-layer tokens as `night\|snow`; DIFFERENT seeded ridge + 48 stars at DIFFERENT placement | **GRACEFUL** (reserved) | `artifacts/night_clear.html` · 48 stars, renders |
| `dawn\|clear` | day gradient | SAME dawn sky-layer tokens as `dawn\|snow`; DIFFERENT seeded geometry | **GRACEFUL** (reserved) | `artifacts/dawn_clear.html` · renders |
| `dusk\|clear` | night gradient | SAME dusk sky-layer tokens as `dusk\|snow`; DIFFERENT seeded ridge + 48 stars at DIFFERENT placement | **GRACEFUL** (reserved) | `artifacts/dusk_clear.html` · 48 stars, renders |

**Completeness:** 8/8 cells enumerated + rendered + verdicted. No sampling.
**No cell broke** (every cell renders a full token-only atmosphere; the harness
double-render byte-diff is green on all 8 — see Determinism below).

## Gaps ordered by visual impact (the before-photo's punch list — now closed by M2-M4)

1. **dawn/dusk were INVISIBLE** (highest impact): both collapsed onto the
   day/night branch, so the two twilight drift anchors SPR-06 needs looked
   identical to their neighbours — no light to drift toward. → Closed: 4 distinct
   dayPart sky ramps, dawn/dusk are now distinct twilight states.
2. **No horizon glow** (high impact): a flat top-to-bottom gradient has no "where
   the light sits" cue — the single biggest "this is a real sky" tell. → Closed:
   per-dayPart `--scene-glow-*` radial pool at the skyline.
3. **Night had no stars** (high impact): a deep-space gradient with an empty sky
   reads as a void, not a night. → Closed: 48 deterministic seeded stars at
   dusk + night (`makeStars`, never `Math.random`).
4. **No aerial perspective** (medium): all peak bands were equally saturated, so
   distance read only from overlap, not value/saturation recession. → Closed:
   `--scene-haze-*` veil over the far band + the 3-plane `Mountainscape` with a
   documented far→near recession (far hazed 0.42 → near un-veiled).
5. **No foreground depth** (medium): the ridge was a single backdrop with nothing
   between it and the viewer. → Closed: `Mountainscape` foreground planes the
   penguin journeys across, parallax-ready for SPR-06.

## Determinism (rigor #3 — the count, not the vibe)

Double-render byte-diff on ALL 8 cells (ProceduralSky stars + Mountainscape
planes): byte-identical. `snapshot-matrix.test.tsx` — "is BYTE-STABLE per cell
across a double render". Star fields are seeded from `fieldSeed(moodKey)` via
`makeStars` (`field.test.ts` — "same seed → byte-identical star field"). The
peak `d` paths in the day artifact are byte-identical to the SPR-04 snapshot —
M2 added light over/under the proven geometry, it did not disturb it.

## Composition decisions a snapshot can't explain (rigor #5)

- **dawn + dusk SHARE the warm twilight glow** (`--scene-glow-dawn` /
  `--scene-glow-dusk` both → `--sun-light`). They are the two anchors SPR-06
  drifts THROUGH; one warm twilight glow used twice keeps the day→night drift
  continuous rather than introducing a second hue that would fight it. (Asserted
  in `palette.test.ts` — dawn/dusk continuity.)
- **The warm light is the WEATHERED sun family, not a loud sunrise.** dawn/dusk
  pull `--sun-light` / `--sun-light-soft` (chroma ~0.36), per the §5.5 voice
  discipline ("aged, not loud") — the same restraint Werner's bill/rod follow.
- **Stars sit in the upper two-thirds only** (`y ∈ [0.02, 0.66]`) so none land
  inside the ground/ridge. (`field.test.ts` — stars in the upper sky.)
- **The night sky is deep in BOTH OS themes.** `--space-*`/`--charcoal-*` are
  promoted to CSS vars with identical day/night values — the SKY is a deep
  surface regardless of OS theme (it is the sky, not a UI card). dayPart, not OS
  theme, drives the sky; OS theme only selects which discrete mood emits today.
- **The STAR colour is a FIXED bright tone, NOT the --ice ramp** (sharpen R2 —
  Defect 1). Because the night/dusk skies are deep in BOTH themes (above), the
  star colour must stay BRIGHT in both — so `--scene-star-{night,dusk,dawn}` pin
  to `--scene-star-base` (#F4F7FA), re-asserted under the dark cascade, rather
  than tracking `--ice-*` (which inverts to near-black under dark and made the
  R1 stars invisible at ~1.04:1). Enforced by a resolved-contrast gate
  (`palette.test.ts` — "night/dusk stars are VISIBLE under the dark cascade",
  ≥3:1 WCAG 1.4.11; the fix clears it at ~15–18:1).
