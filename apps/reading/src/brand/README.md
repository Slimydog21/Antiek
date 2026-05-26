# src/brand/

Werner the penguin lives here.

The single source of truth for the mark is `src/brand/Werner.tsx` — one
SVG React component, four moods (`idle` | `thinking` | `empty` |
`celebrate`), size-driven fidelity, motion in CSS only. Every surface that
shows Werner renders this component; there is no parallel geometry and no
raster mark in the product chrome.

`brand_werner.html` in `docs/ui_redesign_posthog/` is the canonical brand
bible (palette, voice, pose meaning, dos + don'ts).

## Werner.tsx — the four moods

The same penguin geometry drives all four; each mood adds or moves a small
amount of chrome, and the JSDoc in `Werner.tsx` records the load-bearing
numbers (viewBox, bill apex, fidelity threshold, sway timing).

- `idle` — the persistent rail mark (28 px) and the base for the animated
  wrappers. Carries the light idle sway.
- `thinking` — head tilts −6°; four aurora dots pulse right-to-left.
- `empty` — head tilts −6° for blank/first-run states.
- `celebrate` — one-shot raised flipper + sparkle on a completed action.

Fidelity is size-driven: below 48 px is the clean rail/favicon silhouette;
at ≥ 48 px the character details (skeptical eye lid, wing curve, toe hints)
appear. A `MOODS` allowlist plus a dev-only runtime guard reject any fifth
mood string before it can render.

## Motion (CSS only)

Animation lives in `werner/animated/animations.css`; every wrapper imports
it. The idle sway is a 4.2 s breathing cycle; the thinking dots pulse on a
1.2 s stagger; celebrate is an 800 ms one-shot. All of it collapses to a
static frame under `prefers-reduced-motion: reduce`.

## What's in here

```
Werner.tsx                The single-source mark component.
werner/
  animated/               Thin wrappers that compose Werner with motion.
    animations.css        Every keyframe + the reduced-motion collapse.
    WernerThinking.tsx    Idle penguin + external aurora thinking dots.
    WernerWaddle.tsx      Idle penguin with the route-transition waddle.
    WernerCaughtAFish.tsx / WernerSleeping.tsx / WernerTobogganSpinner.tsx
    Animations.stories.tsx, index.ts
  poses/                  Krea-generated reference PNGs (illustration
                          source for the bible; not loaded by the app).
    anchor/               The default + hero anchor poses.
    werner_*_v1_corrected.png   color-corrected pose references.
  marks/                  Out-of-app mark derivatives (avatar, social card,
                          Apple touch icon) + build_marks.py + stack-lockup.svg.
  color_correct.py        PNG color-correction helper (locks near-yellows
                          to the brand sun #F5DF24).
```

The in-app favicon (`public/favicon.svg`) is the Werner silhouette drawn
from `Werner.tsx`'s geometry, not a PNG from `marks/`.

Full guide: `docs/ui_redesign_posthog/brand_werner.html`.

## Restraint rule (non-negotiable)

Werner appears in exactly four slots and nowhere else:

- Rail top (mood="idle", 28 px) — the persistent home affordance.
- AI working states (mood="thinking") — sidecar, start banner.
- Blank / empty states (mood="empty") — no results, first-run.
- Core action completed (mood="celebrate", one-shot) — investigation done, save success.

Never mid-content. Never over controls. Never more than one on screen.
The rule keeps personality from turning into noise; U-05 anti-noise
guard will reference this file. Adding a fifth surface is a brand
decision, not an import.

The idle sway is light (4.2 s cycle) and collapses under
prefers-reduced-motion. All four moods share the same penguin so the
operator never wonders "which Werner is this."

The key numbers (tilt −6°, sway 4.2 s, fidelity threshold 48 px, bill
apex, eye radius) and the one constraint behind each live in the JSDoc of
Werner.tsx.
