# Werner authored curious pose — Cycle 566

Status: verified for stacked transport.

## Decision

`WernerCurious` keeps its public `thinking` semantic and 1,200 ms reaction
contract, but renders the existing authored head-tilt illustration through the
private `WernerAuthoredPose` seam. Semantic identity and illustration choice are
related, not interchangeable.

## Evidence

The prior reaction rotated the generic thinking pose to approximate curiosity.
The brand asset set already includes a transparent head-tilt raster with 24.5%
opaque coverage and subject bounds x=239–774, y=159–900 on its 1024px canvas.
That pose is the brand-bible illustration assigned to curiosity.

## Composition

The reaction boundary exposes `data-werner-mood="thinking"` as inspectable
semantic evidence. Only the curious mark substitutes `headTilt`; happy, dizzy,
and hit continue through the canonical four-mood `Werner` renderer. The outer
reaction owns the accessible name and evidence chrome. Reduced motion retains
the complete still and uses the existing motion-collapse policy.

## Deferred

The toboggan raster was re-audited. Its main connected component includes both
body and speed streaks; the remaining components are dust only. Component
extraction cannot isolate the effects, while color-keying would damage the
body. Tobogganing remains deferred until a faithful authored layering method is
available.

## Proof

Tests must prove the public curious/thinking semantic, exact duration, private
head-tilt source, evidence chrome, isolation from all other reactions, and
source-import boundary. Storybook visual baselines must prove both semantic
reaction and deterministic motion-proof surfaces at 768, 1024, and 1280 pixels.
