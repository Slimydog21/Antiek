# Werner outline-block reaction — cycle decision

Date: 2026-07-14
Sprint: WERNER-ACT SPR-32

## Decision

Emit one `outline_block_committed` experience only after the shared Write
`placeBlock` client decodes a non-empty `outline_block_id`. The sole Werner
reuses the existing curious evidence-card composition.

The episode means “a piece entered this outline.” It does not mean the section,
draft, argument, or writing task is complete. The shared boundary covers the
existing deliberate tap, drag, and voice-to-draft producers. Prose autosave,
block reorder, AI generation, failed transcription, opening Write, and history
loading do not call this boundary and remain silent.

## Proof

- Ten focused and coupled suites pass 82 tests covering delayed success,
  rejected persistence, missing/null/empty/whitespace success identities,
  unchanged valid identity return, tap/drag/voice consumers, the closed
  reaction map, sole-stage translation, latest-wins behavior, cleanup, and
  scene-beat precedence.
- TypeScript, token lint, type-scale lint, production build, Storybook build,
  and the 51-story axe audit pass.
- No visual baseline changed because SPR-32 reuses the already-reviewed curious
  composition without changing its pixels, timing, or reduced-motion still.
- The first GPT-5.6-sol critic found that malformed 2xx bodies could trigger a
  false commit reaction. Identity validation and four negative cases close that
  hole; an independent follow-up returned APPROVE and confirmed the 502
  upstream-contract classification.
- HardenX strict reports LOW with 0 REAL findings and 14 repository-wide
  advisories.

## Withheld authority

No prose-save, reorder, generation, or Speak reaction; cooldown, queue, replay,
payload, generic event framework, new pose, mood, stage, mascot, backend
contract, navigation, provider call, spend, merge, or deployment is authorized
by this decision.
