# Werner night-watch beat — cycle decision

Date: 2026-07-14
Sprint: WERNER-ACT SPR-30

## Decision

Ship one awake, authored night-watch pose when the existing scene authority
crosses into night. This completes the closed civil-light episode set:
`nightfall | daybreak | dusk-settle`. It does not create an episode scheduler,
registry, queue, persistence layer, replay mechanism, provider runtime, or
fourth transition.

The sole live mascot consumes each scene sequence once. Product reactions,
drag, directed travel, station ownership, and true long-rest waking retain
precedence; a preempted night beat is consumed rather than replayed later.
Reduced motion shows the same awake semantic pose without animation.

## Proof

- The 1254×1254 ChatGPT Image RGB source and 1024×1024 runtime RGBA asset have
  recorded SHA-256 hashes. The topology cut removes all partial-alpha and pale
  neutral boundary pixels while preserving an opaque warm-white belly.
- The transition and mascot suites prove monotonic nightfall/daybreak/dusk
  sequences, contiguous dawn-only compatibility IDs, one-shot consumption,
  product preemption, reduced-motion stillness, and awake rather than sleeping
  or waking semantics. The focused four-suite gate passes 37 tests; the coupled
  ten-suite gate passes 81 tests.
- TypeScript, token lint, type-scale lint, production build, Storybook build,
  and the 51-story axe audit pass.
- The fidelity plate has regenerated zero-diff LostPixel baselines at 768,
  1024, and 1280 pixels, repeated twice after the alpha correction.
- HardenX strict reports LOW with 0 REAL findings and 14 repository-wide
  advisories. A fresh GPT-5.6-sol critic identified the pale-matte weakness;
  after correction, an independent follow-up returned APPROVE with no subject
  erosion, checker residue, or hard-edge regression.

## Withheld authority

No generic performance runtime, provider call, video stream, background
generation, new clock, fourth scene episode, duplicate mascot, route change,
network spend, merge, or deployment is authorized by this decision.
