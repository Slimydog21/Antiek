# Werner authored sleeping pose — Cycle 565

Status: implemented locally; transport awaits verification.

## Decision

Private authored illustration poses are distinct from the four public product
moods. `WernerAuthoredPose` owns their source map; sanctioned wrappers own
choreography and accessibility. The first admitted private pose is `sleeping`.

## Evidence

The brand bible already defines seven canonical illustrations and separately
constrains product use. The live sleeping wrapper nevertheless rendered the
lost/empty mood even though a transparent authored sleeping raster exists. Its
connected-component bounds provide a clean source-native seam: authored Z
marks end at y=394 and the body begins at y=396 on the 1024px source.

## Composition

Motion-allowed sleep renders the same raster twice, clipped into disjoint body
and Z bands. Existing 2.4 s keyframes animate those bands independently.
Reduced motion renders the complete raster once, with no animation classes.
The wrapper supplies one accessible name; every raster layer is decorative.

## Deferred

The tobogganing raster's speed marks overlap its body horizontally. Migrating it
now would either duplicate speed effects or require an unproven destructive
asset split. It remains deferred until a faithful layering method is specified.

## Proof

Tests must distinguish sleeping from empty, prove identical layer sources and
exact clip boundaries, prove the single-layer reduced path through `EmoteView`,
and preserve the Cycle 563 empty/dizzy crop. Storybook and visual baselines must
show complete sleeping stills at 48, 96, and 120 px.
