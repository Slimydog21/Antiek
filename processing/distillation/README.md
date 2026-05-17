# processing/distillation/

Consolidated document generation. Takes ingested + extracted material
across many chunks and produces longer-form distillations suitable for
downstream synthesis.

## When this runs

- After a sub-question retriever surfaces a large evidence set —
  distill before passing to the synthesizer.
- At the end of Phase 3 (extract) → before Phase 4 (connect).
- During Phase 8 (compound) — distillation of the cycle's findings is
  the material that gets merged into domain skills.

## Routing

Pro-tier or synthesis-tier model depending on the distillation's
downstream use. Configured per-role in `substrate/dispatch/config.yaml`.
