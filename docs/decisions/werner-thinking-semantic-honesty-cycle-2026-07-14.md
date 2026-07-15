# Werner thinking semantic honesty — Cycle 564

Status: implemented locally; stacked transport pending verification.

## Decision

`WernerThinking` renders `<Werner mood="thinking">`. The canonical four-mood
component remains the only live identity seam; the wrapper retains its four
external aurora dots and accessible status name.

## Why

The exported component, JSDoc, and product copy all promised a thinking state,
but the implementation rendered idle despite an existing canonical thinking
pose. This was semantic drift, not an asset gap. Correct delegation is smaller
and more honest than adding animation or generating new art.

## Deferred deliberately

Sleeping and tobogganing rasters exist but are not public canonical moods.
Adopting them would require deciding whether private animation poses can coexist
with the four-mood API without forking identity. That decision is outside this
cycle and must not be smuggled in through a wrapper.

## Proof contract

- Runtime test distinguishes the thinking asset from idle.
- The status keeps one accessible name; all decorative imagery/dots stay hidden.
- Storybook shows the supported 24, 40, and 64 px sizes.
- Existing CSS reduced-motion guard continues to collapse every thinking dot.
- Type, focused tests, production/Storybook builds, visual inspection, security
  triage, and independent adversarial review must pass before transport.
