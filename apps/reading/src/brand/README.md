# src/brand/

The Antiek brain lives here.

The single source of truth for the live mark is `src/brand/BrainMascot.tsx`:
one React component mapping four moods (`idle` | `thinking` | `empty` |
`celebrate`) to transparent, brand-locked Krea pose rasters from
`mascot-brain/`. Every live surface delegates the mascot's body to this
component. Animated wrappers add only motion and small semantic accents.

`mascot-brain/PROFILE.md` is the canonical character bible: concept, design
spec, palette, consistency protocol, and shot provenance for every future
generation. (The penguin-era `docs/ui_redesign_posthog/brand_werner.html` is
historical; the brain replaced the penguin because Antiek's promise is AI that
amplifies the human brain, never replaces it — the mascot is the thesis.)

## BrainMascot.tsx — the four moods

The canonical mood-to-pose map is the mascot's identity seam. Wrappers must
request the mood they claim rather than substituting another pose.

- `idle` — persistent rail mark and gentle breathing sway.
- `thinking` — authored thinking pose for AI-working states; wrappers may add
  four aurora dots pulsing right-to-left.
- `empty` — authored sleepy pose, for blank/first-run states.
- `celebrate` — authored excited pose for completed core actions.

The same source pose scales to each surface's requested size. A `MOODS`
allowlist plus a development runtime guard rejects any fifth mood string
before it can render.

## BrainMark.tsx — the rail mark

A geometric line-drawn brain (pure inline SVG, design tokens only, no
raster) for the NavRail home button at 24–28 px. Idiom lockup: the **vector
line brain** owns in-app chrome marks; the **Krea raster** owns the mascot
poses, favicon, avatars, and social cards. Two idioms of one mark — do not
mix them on one surface.

## BrainPresence.tsx — ambient presence

A large (default 420 px), very-low-opacity (0.08) brain drifting slowly
behind app content, mounted in AppShell above the living scene and below the
content column; `aria-hidden` and `pointer-events: none`. It is ambience,
not chrome — and because it is always mounted, no route may add a second
large mascot: the restraint rule's "never more than one on screen" includes
the presence layer.

## Motion (CSS only)

Animation lives in `mascot-brain/brainMascot.css`; every wrapper imports it.
The idle sway is a gentle breathing cycle, the blink fires at irregular
~3–6 s intervals, and hover provokes a blink. Every animation collapses to a
static frame under `prefers-reduced-motion: reduce`. (The mascot-era
keyframes in `mascot/animated/animations.css` serve only the legacy wrappers
below.)

## What's in here

```text
BrainMascot.tsx           Canonical live mark and four-mood pose map.
BrainMark.tsx             Geometric line-brain rail mark (NavRail home).
BrainPresence.tsx         Ambient low-opacity background brain (AppShell).
mascotSceneMap.ts         Scene mood → mascot mood map. Note: no call site
                          passes `scene` today; the map is exercised only by
                          tests (dead public seam, pending wire-or-delete).
mascot-brain/             Krea pose rasters + brainMascot.css.
  PROFILE.md              The character bible (design spec, palette, QA).
  authored/               Authored variant poses (head-tilt, sleeping).
marks/                    Out-of-app brain derivatives (favicon, social card,
                          avatars) + build_brain_marks.py.
mascot/                   Penguin-era animated wrappers and pose sources
                          (Werner* → Brain*/Mascot* in the 2026-09-21 naming
                          purge), still rendering the brain via delegation.
```

The favicon chain (`public/mark-32.png`, `public/favicon.svg`,
`public/mark-180.png`) renders the Krea raster idiom; it does not replace
the canonical in-product component.

## Restraint rule (non-negotiable)

The brain appears in exactly four slots and nowhere else:

- Rail top (`mood="idle"`, 28 px) — persistent home affordance.
- AI working states (`mood="thinking"`) — sidecar and start banner.
- Blank / empty states (`mood="empty"`) — no results and first-run.
- Core action completed (`mood="celebrate"`, one-shot) — investigation done
  and save success. Celebrate is a one-shot beat (CelebrateBurst), never a
  persistent pose.

Never mid-content. Never over controls. Never more than one on screen
(BrainPresence counts). Adding a fifth surface or mood is a brand decision,
not an import.
