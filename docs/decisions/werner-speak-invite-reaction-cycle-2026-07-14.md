# Werner Speak invitation reaction — cycle decision

Date: 2026-07-14
Sprint: WERNER-ACT SPR-33

## Decision

Emit one `speak_invite_committed` experience only after the creator-side Speak
`inviteByEmail` request resolves. The sole Werner reuses the existing happy
composition.

The episode means “Antiek accepted the invitation request.” It does not mean
the email was delivered, opened, or accepted; consent was granted; a guest
participated; or a contribution was completed. The unauthenticated guest flow,
share-link setup, polling, assembly, publishing, and payouts remain silent.

## Proof

- Nine coupled suites pass 78 tests; the focused four-suite rerun passes 29.
  Pending completion and rejected-request silence are both pinned at the real
  creator callback.
- TypeScript, token lint, type-scale lint, production build, Storybook build,
  and the 51-story axe audit pass. No visual baseline changed because the happy
  composition, timing, and reduced-motion still are unchanged.
- A fresh GPT-5.6-sol critic found failure-unsafe listener cleanup and an
  app-local generated audit artifact. Both were removed; a second sharpen made
  teardown unconditional with `try/finally`; the final review returned APPROVE.
- HardenX strict reports LOW with 0 REAL findings and 14 repository-wide
  advisories. This repository has no `corpus.toml`, so corpus certification is
  unavailable and the result remains advisory under the skill contract.
- The full host-Node suite reached 1,846 passing tests but retains 36 unrelated
  baseline failures: 35 from the known jsdom `localStorage` incompatibility and
  one pre-existing semantic-reaction motion-baseline mismatch. The scoped
  dependency graph is green and no unrelated harness was changed.

## Withheld authority

No guest reaction, delivery receipt, invitation acceptance, consent inference,
share-link reaction, assembly reaction, cooldown, queue, replay, payload,
generic event framework, new pose, mood, stage, mascot, backend contract,
provider call, spend, merge, or deployment is authorized by this decision.
