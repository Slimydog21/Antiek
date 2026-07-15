# Werner source-read reaction — cycle decision

Date: 2026-07-14
Sprint: WERNER-ACT SPR-31

## Decision

Emit one `source_read_committed` product experience only after the existing
`source.read` typed-event write resolves successfully. The sole Werner reuses
the existing happy archival-verification composition.

The episode means “this reading evidence was recorded.” It does not mean the
book, paper, chapter, or source was completed. The existing 30-second focused
dwell and two-page threshold remains a low engagement signal. Opening,
scrolling, page turns, threshold crossing before persistence, rejected writes,
and historical event loading remain silent.

## Scope adjudication

GPT-5.6-sol recommended this single Read edge. MiMo V2.5 Pro recommended two
Write producers plus a new cooldown mechanism. Read was selected because its
persisted event is already rare, authoritative, and naturally coalesced by the
reading session. Adding reaction throttling policy before a demonstrated spam
problem would broaden the system without improving this proof.

## Proof

- Seven focused and coupled suites pass 62 tests covering delayed commit,
  failed-write silence, metadata-only payloads, the closed experience map,
  sole-stage translation, latest-wins choreography, cleanup, and scene-beat
  precedence.
- TypeScript, token lint, type-scale lint, production build, Storybook build,
  and the 51-story axe audit pass.
- No visual baseline changed because SPR-31 reuses the already-reviewed happy
  composition without changing its pixels, timing, or reduced-motion still.
- A fresh GPT-5.6-sol critic returned APPROVE. HardenX strict reports LOW with
  0 REAL findings and 14 repository-wide advisories.

## Withheld authority

No Write or Speak producer, cooldown, queue, replay log, generic event
framework, payload-bearing reaction, new pose, mood, animation, stage, mascot,
dwell-threshold change, chunk-ID backend work, SiteSee change, provider call,
spend, merge, or deployment is authorized by this decision.
