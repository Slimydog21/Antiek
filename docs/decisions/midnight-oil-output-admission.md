# Midnight Oil output admission

Status: executable decision for the research-reading spine output gate

## Problem

Midnight Oil deliberately deposits terminal, timed-out, and budget-halted work
so partial work is recoverable. The fallback deposit path currently turns an
absent worker result into synthetic prose and insights such as `Investigated:`
and `Progress on:`. Those strings then become durable HTML and twin notes even
though no research result supports them.

Operational recovery and epistemic acceptance are different concerns. An empty
run should remain visible without being promoted into a claim that work
occurred.

## Decision

When a worker returns no body or insights:

- preserve the terminal deposit with the explicit body `No research result was
  returned for: …`;
- create no fallback insight;
- retain an open question derived from the approved goal so the operator can
  resume the work;
- preserve an already-completed spawn as the durable content authority during
  retry recovery;
- render route and source receipts under an explicit `Operational evidence`
  label, never allowing receipt text alone to count as a research result;
- keep the existing idempotent HTML/twin deposit and status receipt behavior.

Actual returned insights remain unchanged in this slice.

## Required proofs

- An empty returned step produces no insight twin.
- A goal-only deposit produces no insight twin.
- Both paths preserve an honest HTML artifact and an open question.
- Whitespace-only and receipt-only results take the same honest empty path.
- Receipt-only recovery keeps its audit identifiers under the operational label.
- A retry cannot overwrite a completed spawn's returned prose or findings.
- Later results in the same deposit batch still update their shared spawn.
- Neither path contains the old `Investigated:` or `Progress on:` claims.
- Existing returned worker prose and findings still deposit idempotently.

## Deferred claim-to-source gate

A citation-count floor is not sufficient to admit actual returned claims. One
source receipt attached to a step does not prove that every insight or paragraph
is supported by it. The next gate must version a research acceptance contract
at approval time and carry claim-to-receipt identifiers in
`MidnightOilStepEvidence`. Deposit may retain unsupported material as explicitly
unverified operational output, but graph promotion must require verified claim
coverage and recheck canonical receipt identity before its first write.

This extends rather than duplicates the completed execution controls: budget,
leases, terminal settlement, replay, and effect receipts prove how a run was
authorized and persisted; they do not prove that a particular claim is grounded.
