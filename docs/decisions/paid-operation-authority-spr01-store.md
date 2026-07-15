# Paid Operation Authority SPR-01 Store

Date: 2026-07-15

## Decision

Implement a fresh, provider-inert SQLite authority store in
`substrate/paid_operations/` rather than extracting the historical Midnight Oil
runtime.

## Evidence

- Root contract: `docs/htmlspec/paid-operation-authority/index.html`.
- Sprint contract: `docs/htmlspec/paid-operation-authority/sprint-01-authority-store.html`.
- Current owner convention: `substrate/auth/magic_link.py` documents session
  `user_id` as the `owner_user_id` convention; graph schemas already carry
  `owner_user_id`.
- Current product-specific authority evidence: `substrate/multimedia/execution_authorization.py`
  and `substrate/multimedia/execution_authorization_issuer.py` show useful
  replay/conflict patterns, but bind to multimedia asset/revision/provider
  receipts and DuckDB budget-ledger composition.
- Historical evidence named by the spec:
  `caffen/mo-authorization-live-convergence@802d2e0e`. It remains evidence
  only; this implementation does not cherry-pick it.

## Rationale

SPR-01 needs a shared authority record for multiple paid operation kinds. The
existing multimedia issuance path is already execution-adjacent and product
specific. Reusing it would import provider-bound receipt assumptions before
the consent, queue, lease, budget and reconciliation sprints establish the
shared substrate.

The new store accepts owner/account identity only through the internal
`Subject`, scopes identity to `(account_id, owner_user_id, operation_id)`,
derives canonical bytes with the frozen v1 intent contract, and persists no
queue row, lease, provider result, settlement, reconciliation result, or
product projection. SPR-01 CAS has a closed patch map: only
`intent_created -> consent_issued` may populate consent metadata, and every
transition requires monotonic `updated_at_ms`.

## SPR-02 Trust Boundary

SPR-02 may trust that `(account_id, owner_user_id, operation_id)` identifies an
immutable canonical intent row, exact replay returns the same row, the same
operation ID can be reused by distinct owners/accounts, foreign reads/CAS do
not enumerate another subject's row, and every state mutation is a versioned
owner/account-scoped CAS under `BEGIN IMMEDIATE`.
