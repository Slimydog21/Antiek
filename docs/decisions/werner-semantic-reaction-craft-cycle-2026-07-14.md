# Decision: semantic props, canonical Werner

Date: 2026-07-14
Cycle: 561

## Decision

Keep the existing six-event vocabulary, stage timing, and four canonical Werner
moods. Replace only the four misleading visual aliases with dedicated semantic
compositions. Werner remains the canonical raster identity; small token-native
SVG props explain the event.

## Why

The old aliases were mechanically convenient but visually untruthful: a
toboggan did not mean “recover from failure,” and a caught fish did not mean
both “research verified” and “bumped a control.” Distinct props let the user
read the event before interpreting animation while avoiding an uncontrolled
fifth-pose expansion.

## Rejected

- New generated runtime poses: identity drift, load cost, and a fifth-mood fork.
- A generic particle system: decorative motion without semantic information.
- New event kinds or producer edits: this is visual truth, not product authority.
- Runtime storyboard bitmap: inaccessible and contrary to Antiek's HTML vision.

## Consequences

Curious, happy, dizzy, and hit now have one-shot compositions synchronized to
the unchanged stage duration table. Happy deliberately uses the clean idle
identity rather than the fish-bearing celebrate raster. Reduced motion
preserves the meaningful prop in a still frame. Thinking and sleeping retain
their established marks.
