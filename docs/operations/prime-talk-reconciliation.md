# Prime Talk reconciliation

Prime `STARTED`, `USAGE_OBSERVED`, and `UNKNOWN` operations retain their hold.
An ordinary signed owner may POST an empty body to the reconcile endpoint only
to refresh status; that action never releases money.

An operator authenticated with the bearer token or Cloudflare service token may
resolve an operation after checking the first-party provider billing console:

- `confirmed_no_charge` requires a SHA-256 digest of the exported billing/audit
  evidence and changes a reconcilable operation to `cancelled`, releasing its hold.
- `exact_usage` requires the same evidence digest plus exact token counts, cost,
  observation time, and provider request/event identifiers. Matching usage within
  the authorization settles `succeeded`; an overrun remains `unknown` with its
  observed charge and hold for manual financial review.

Never use reconciliation to estimate usage, retry a provider call, or release an
ambiguous hold without provider evidence. Preserve the provider export outside
Antiek under the digest supplied to the endpoint.
