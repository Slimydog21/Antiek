# src/brand/

Werner the penguin lives here.

The single source of truth for the live mark is `src/brand/Werner.tsx`: one
React component mapping four moods (`idle` | `thinking` | `empty` |
`celebrate`) to transparent, brand-colour-locked Krea pose rasters. Every live
surface delegates Werner's body to this component. Animated wrappers add only
motion and small semantic accents.

`brand_werner.html` in `docs/ui_redesign_posthog/` is the canonical brand bible
for palette, voice, pose meaning, and usage restraint.

## Werner.tsx — the four moods

The canonical mood-to-pose map is Werner's identity seam. Wrappers must request
the mood they claim rather than substituting another pose.

- `idle` — persistent rail mark and restrained 4.2 s breathing sway.
- `thinking` — authored thinking pose for AI-working states; wrappers may add
  four aurora dots pulsing right-to-left.
- `empty` — authored lost pose, locally reframed for blank/first-run states.
- `celebrate` — authored caught-a-fish pose for completed core actions.

The same source pose scales to each surface's requested size. A `MOODS`
allowlist plus a development runtime guard rejects any fifth mood string before
it can render.

## Motion (CSS only)

Animation lives in `werner/animated/animations.css`; every wrapper imports it.
The idle sway uses a 4.2 s cycle, thinking dots use a 1.2 s stagger, and
celebration is an 800 ms one-shot. Every animation collapses to a static frame
under `prefers-reduced-motion: reduce`.

## What's in here

```text
Werner.tsx                Canonical live mark and four-mood pose map.
werner/
  WernerAuthoredPose.tsx  Private sleeping + head-tilt source map.
  animated/               Thin wrappers that compose Werner with motion.
    animations.css        Keyframes and the reduced-motion collapse.
    WernerThinking.tsx    Thinking pose + external aurora thinking dots.
    WernerWaddle.tsx      Idle pose with route-transition waddle.
    WernerSleeping.tsx    Authored sleep body + Z layers from one source.
    WernerCaughtAFish.tsx / WernerTobogganSpinner.tsx
    Animations.stories.tsx, index.ts
  poses/                  Krea-generated source and transparent runtime PNGs.
    anchor/               Default runtime pose + hero source art.
    werner_*_v1_corrected.png    Colour-corrected provenance sources.
    werner_*_v1_transparent.png  Alpha-cut runtime candidates and live poses.
  marks/                  Out-of-app mark derivatives and build tooling.
  color_correct.py        Locks near-yellows to brand sun #F5DF24.
```

The favicon (`public/favicon.svg`) is a separate small-format derivative; it
does not replace the canonical in-product component.

Full guide: `docs/ui_redesign_posthog/brand_werner.html`.

## Restraint rule (non-negotiable)

Werner appears in exactly four slots and nowhere else:

- Rail top (`mood="idle"`, 28 px) — persistent home affordance.
- AI working states (`mood="thinking"`) — sidecar and start banner.
- Blank / empty states (`mood="empty"`) — no results and first-run.
- Core action completed (`mood="celebrate"`, one-shot) — investigation done
  and save success.

Never mid-content. Never over controls. Never more than one on screen. Adding a
fifth surface or mood is a brand decision, not an import.

Authored animation poses are private illustration sources, not public moods.
`WernerAuthoredPose.tsx` centralizes those sources so wrappers cannot import
rasters ad hoc. Sleeping and curious head-tilt are live through that seam.
Tobogganing remains a candidate until its baked speed marks can be separated
from the overlapping body without duplicate effects.
