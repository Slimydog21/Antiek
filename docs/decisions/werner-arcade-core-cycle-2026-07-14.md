# Werner arcade core cycle — 2026-07-14

## Decision

Recover the dirty session arcade prototype as a narrow engine-and-cartridge
foundation before exposing any game in product. The branch owns only fixed-step
scheduling, canvas input, seeded randomness, two private state machines,
token-derived drawing, and tests. Cabinet, wait host, product routes, research
readiness, generated art, scene hotspots, and shell changes remain separate.

This distinction is product truth: the current primitive canvas drawing proves
mechanics, not the final Club Penguin-inspired or arcade-zombies visual craft.

## Recovered defects

The read-only co-CEO audit accepted the slice but rejected the prototype as
merge-ready. It identified lost and replayed input edges, dead reduced-motion
input, window-global keyboard control, responsive pointer drift, raw color
literals, false configurable lives, repeated terminal score writes, and a
simulation helper that skipped teardown.

The hardened contract samples only when a fixed step can consume input and
delivers edges to one substep. Canvas keys are focus-scoped, pointer coordinates
are logical, reduced motion advances only on explicit input, configured lives
survive restart, terminal persistence is transition-only, helpers teardown in a
`finally` block, and drawing imports the canonical Antiek token module.

## Authority boundary

No owned file may import navigation, App/AppShell, Deep Research, Werner stage,
browser storage, telemetry, a provider API, or any content/spend surface. A
later host sprint must independently prove opt-in, readiness teardown,
accessibility, visual craft, and live browser behavior.

## Verification status

The sharpened arcade suite passes 8 files and 45 tests. Prettier, TypeScript,
token lint, type-scale lint, production build, and bundle budget pass. Hardenx
reports LOW with 0 REAL findings. MiMo 2.5 Pro first returned **REVISE** for a
reduced-motion catch bonus and missing voluntary-exit score report; both defects
and every low-severity safety-net finding were repaired. Its exact delta reread
reproduced all 45 tests and returned **ACCEPT** with no remaining regression.

Remote checks remain required before transport is complete. Live product visual
acceptance is not applicable to this private core because no route, cabinet, or
wait host exposes it yet.
