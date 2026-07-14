# Write Field Kit — cycle decision (2026-07-15)

## Decision

Restore the evidence-to-outline loop below the desktop breakpoint with one
responsive field-kit tray that reuses `BlockRepository`, then require an exact
section seam before committing. Existing blocks use the same keyboard seams for
movement. Desktop retains its one repository sidebar and native drag path.

The existing place/move endpoint shapes remain authoritative. Their index now
means final visual position: touched sections normalize legacy sparse or
duplicate ordering, insert shifts occupied positions, move compacts and inserts
once, and removal closes the vacated seam. Typed events record the resolved
index.

## Why this slice

Write instructed tablet users to use a repository that CSS had removed. This
was a real broken workstation loop, not a decorative opportunity. A single
brass field-kit tab belongs to the established alpine scriptorium language and
keeps HTML controls, text, provenance, focus, and persistence authoritative.

## Boundaries

- No generated image, Werner reaction, cursor behavior, animation, provider,
  model, spend, analytics, new endpoint, dependency, merge, or deployment.
- One repository instance is mounted at a time across the `lg` breakpoint.
- Failed persistence retains the placement intent; successful persistence is
  never reclassified as failure because a subsequent view refresh rejects.
- Claim/question semantics and node identity survive tap and native drag.

## Evidence

- 55 coupled frontend tests and 45 backend/API tests passed; the final focused
  commit-boundary subset contained 30 passing tests.
- TypeScript, token lint, type-scale lint, production build, Storybook build,
  diff hygiene, and the 52-story axe audit passed.
- HardenX strict: LOW, 0 real findings, 14 repository-wide advisories. Corpus
  certification is unavailable because this checkout has no corpus file.
- GLM-CC ultracode was invoked read-only but returned HTTP 429. Multiple fresh
  GPT-5.6-sol adversarial passes drove repairs; the final pass returned APPROVE.
- The in-app browser had no available target, so no live-browser equivalence is
  claimed. The deterministic Storybook plate and axe result are the visual and
  accessibility evidence for this cycle.
