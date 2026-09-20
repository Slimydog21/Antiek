# Werner product reaction bus cycle — 2026-07-13

## Decision

Werner now notices six real product experiences through one shell-owned,
runtime-validated event boundary. Product surfaces emit semantic notifications;
only `PenguinMascot` translates them through the existing single
`WernerStage`. No producer receives stage, position, cursor, navigation,
network, spend, or content-mutation authority.

The contract is deliberately edge-triggered. A highlight emits once per open
selection episode, start emits only after a successful launch action, and
pointer idle emits only the active-to-idle edge. Research polling may emit a
new authoritative terminal outcome but never reconstructs launch or replays a
historical outcome on mount. This prevents polling cadence, reconnects, route
remounts, and browser `selectionchange` noise from replaying animation.

## Closed mapping

- highlight → curious
- deep-research start → thinking
- deep-research complete → happy
- deep-research error → dizzy
- pointer idle → sleeping
- shell failure → dizzy

Unknown or malformed browser events are ignored. The mapping cannot be
overridden by callers.

## Scope boundary

This slice does not adopt the dirty arcade cartridges, research wait host,
generated session images, scene hotspots, Flipbook streaming experiment, or
Werner pose replacements. Those are separate systems with separate ownership
and acceptance gates. It adds no dependency or runtime image.

## Adversarial sharpening

Successive independent Codex reviews returned **REVISE** and found real
edge defects. The sharpened contract:

1. celebrates only when every terminal research is `done`; `failed` and
   `budget_halted` become error, while user-stopped work makes no outcome claim;
2. baselines initial and changed-session snapshots instead of replaying them;
3. emits start at successful launch, eliminating cold-load listener ordering;
4. seeds pointer idle from its current level, eliminating startup and
   reduced-motion-toggle false edges;
5. wires both successful launch boundaries and treats partial failure or budget
   halt as error immediately;
6. claims local-launch provenance when the monitor mounts, expires abandoned
   provenance, and never reconstructs start from polling;
7. treats drag, excursion, and visibility as eligibility gates rather than
   pointer-edge authority, including hidden-tab return; and
8. remounts polling and reaction state for a successful relaunch even when the
   backend reuses its deterministic session ID.

## Verification status

Focused product-reaction behavior is green (9 files, 55 tests); the wider
Werner/mascot/FloatMenu/deep-research/toast neighborhood is green (34 files,
315 tests). TypeScript, token lint, type-scale lint, production bundle-budget
check, and Storybook build are green. Hardenx reports LOW with 0 REAL findings.
The final different-lineage Codex merge-bar review returned **ACCEPT** with no
findings after the eight sharpening rounds above.

The repository-wide test command passed 1,538 tests and failed 35 pre-existing
localStorage tests because Node 25.6.1 starts Vitest workers with an invalid
`--localstorage-file` path; the same isolated persistence test fails without
this diff. This slice does not alter that environment/toolchain baseline.

Live appearance is **NOT PROVEN** until the in-app browser can exercise real
highlight, research, failure, idle, and reduced-motion paths at multiple
viewport sizes.
