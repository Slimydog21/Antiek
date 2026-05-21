# src/brand/

Werner the penguin lives here.

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

Components in `src/components/navigation/NavRail.tsx` use an inline
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
