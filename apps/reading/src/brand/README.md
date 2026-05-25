# src/brand/

Werner the penguin lives here.

The single source of truth for the mark in the product is
`src/brand/Werner.tsx` (mood="idle" | "thinking" | "empty" | "celebrate",
size-driven fidelity, CSS motion only). The old inline ellipse stack
in NavRail is gone; the animated pose components remain for legacy
call sites until U-04 wires the moods.

`brand_werner.html` in `docs/ui_redesign_posthog/` is the canonical
brand bible (palette, voice, pose meaning, dos + don'ts). This
directory is the runtime asset side: the Krea-generated pose PNGs,
the marks build pipeline, and the in-app components that reference
them.

## What's in here

```
werner/
  poses/                  Krea PNGs — one per pose, plus *_corrected.png
                          (PIL pass that locks yellow pixels to #F5DF24).
    anchor/               The "default" and "hero" anchor poses + their
                          generation candidates (v1 → v5). The picked
                          winner for each is the v5 file.
    werner_caught_a_fish_v1{,_corrected}.png
    werner_head_tilt_v1{,_corrected}.png
    werner_lost_v1{,_corrected}.png
    werner_sleeping_v1{,_corrected}.png
    werner_thinking_v1{,_corrected}.png
    werner_tobogganing_v1{,_corrected}.png
  marks/                  Mark derivatives + their build script.
    build_marks.py        PIL script that produces favicon-32, mark-180
                          (Apple touch icon), avatar-400, social-card-1200,
                          and the day/night stack lockup with the Antiek
                          wordmark.
    mark-32.png
    mark-180.png
    avatar-400.png
    social-card-1200.png
    stack-lockup.svg      Werner + the Antiek wordmark, sun-yellow
                          underline. Used by README hero + the optional
                          marketing splash.
  color_correct.py        Single-PNG color-correction helper. Replaces
                          the Krea-output near-yellows with the locked
                          #F5DF24 brand sun.
```

## Naming + usage

Components in `src/shell/NavRail.tsx` use an inline
SVG mark (the abstract little penguin head). For full hero rendering
(login splash, README, social cards), use the PNG files directly
via `<img src={...} />`.

The pose PNGs are the source of truth. There is no per-pose React
component on disk — Werner ships as raster assets to preserve the
hand-illustrated feel. (The original brand spec called for one TSX
component per pose; that was pivoted to Krea-generated PNGs after the
first SVG attempt was deemed "not cute enough" by the operator.)

## Discipline

- **Never recolour** the coat or belly. Bill + feet may shift between
  day-ember and night-ember; nothing else moves.
- **Never compose** Werner with other characters or mascots.
- **Never rotate** the hero pose.
- **Never animate** Werner. Werner waddles. Werner does not party.
- The pose library is fixed at 7 + anchor. Adding poses is a brand
  decision, not a code change — propose via the brand spec first.

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

The numeric choices (tilt -6°, sway 4200 ms, fidelity threshold 48 px,
bill apex at 15.7 in the 32-unit viewBox, eye r 1.05, head proportions)
carry hard-to-vary derivations in the JSDoc of Werner.tsx. They were
cross-checked against live 28 px CanonicalMoods renders; none can move
by more than a few tenths without destroying either the cute-emperor
reading at rail size or the deadpan Herzog voice.

Abstract-mark alternative (full balanced steelman). A pure three-ellipse
plus minimal triangle stack with no penguin intent and no mood/fidelity
logic would win on bundle size, perfect 16 px favicon legibility, and
strict logo reductionism — it is the defensible minimalist position and
would have satisfied a "mark-only, no mascot personality" requirement.
The thesis that prevailed weighs the companion reading more heavily:
Werner is the single emperor who broke from the colony and walks into
the interior toward certain death; the rail mark at 28 px is the surface
the operator sees constantly and it must transmit that specific quiet,
deadpan companionship rather than a generic Antarctic dot. An abstract
mark would sever the emotional through-line at the exact place the
operator needs it most. The concrete geometry chosen is the smallest
form that still resolves as "cute emperor penguin with distinct compact
silhouette and prominent high-contrast yellow bill" at 28 px while
scaling to 120 px character without caricature. Both minimalism and
companion theses were evaluated on their merits; the companion reading
was selected because Antiek is a research workstation whose brand
promise is quiet fellow-travelling into the unknown, not a generic
productivity surface. The decision and all derivations are recorded
here and in Werner.tsx so the next operator can re-litigate with the
original evidence in hand.
