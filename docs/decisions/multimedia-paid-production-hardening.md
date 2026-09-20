# Paid production hardening requires byte authority

Status: accepted for MSR-04 execution, 2026-07-14.

## Decision

A registered paid video is hardening-authoritative only when one compound
authority contains both independently signed views at the same cutoff:

1. `direct_settled_provider_executions`: every settled direct execution on the
   exact parent revision.
2. `production_byte_contributing_settled_provider_executions`: the exact
   selected visual and narration-child executions proven to have produced the
   current registered bytes.

The totals overlap legitimately and are never added, substituted, or renamed
as a provider invoice. The compound authority is mutually exclusive with
`local_registered_zero_external_provider_charge`.

## Why now

MSR-02's signed production-byte projection has no hardening consumer. The
current paid path can accept parent-revision accounting without proving that
the current receipt, selected visuals, and narration children are settled.
Production registration also retains an older hardening report, allowing a
pre-registration status to appear current after the bytes change.

Activating learned visual routing is deferred. Its evidence remains advisory,
its minimum cohort thresholds may not be met, and automatic route mutation
needs a separate rollback, exploration, and causal-evaluation decision. Closing
an existing ship-authority hole has higher value and lower blast radius.

## Cardinality

- Unregistered paid video or audio: the existing direct snapshot may satisfy
  only the pre-production cost gate.
- Registered paid video: direct snapshot and production-byte projection are
  both required in one compound authority.
- Registered local video or audio: local-zero evidence only.
- Registered paid audio: blocked until a separate audio byte-closure exists.
- No report may combine local-zero evidence with any paid authority.
- Legacy reports reopen, but current registration and revision state determine
  whether their status remains authoritative.

Projection-only paid video is deliberately unsupported. An unavailable direct
snapshot conflates an empty exact scope with read/schema/authority failure, so
it cannot prove zero direct parent spend. A future signed direct-scope absence
authority may unlock child-only paid production without weakening MSR-01.

## Composition rules

- Capture one timezone-aware instant and require byte-identical child cutoffs.
- Use a dedicated production-projection key, pairwise independent from provider
  execution, direct snapshot, narration, and local-zero signing keys.
- Reopen and verify both children independently, then cross-bind owner digest,
  asset, revision, cutoff, and current production receipt digest.
- Re-read the current asset under the store write lock before persisting. A
  changed revision or production link is a conflict.
- Attaching either video or audio production clears prior hardening authority.
- Conflict is terminal. Only direct evidence unavailability may reach local
  evidence, and a registered paid path never downgrades to local zero.

## Non-goals

No provider call, reconciliation, settlement, recovery, production,
registration, routing mutation, rights automation, publication, second ledger,
or paid-audio byte closure.

## Rejected alternatives

- Projection instead of direct snapshot: loses total parent-attempt spend.
- Projection-only when no direct rows are found: absence is not yet proven.
- One MAC key for both children: weakens domain separation and key rotation.
- Persisting two unrelated top-level paid authorities: omits their cross-binding
  and invites callers to treat them as alternatives or sum their totals.
- Learned routing first: crosses an advisory boundary while current ship
  authority remains incomplete.
