# ANT-RHC SPR-04 handoff

Status: implemented, independently reviewed  
Implementation commit: `c54d49dde`

## Operator contract

- `POST /research/plans/{root_id}/spend-preview` returns server-owned USD eligibility,
  reasons, and projection assumptions. It never issues authority and exposes no rates,
  provider credentials, run ids, or plan digests.
- `POST /research/plans/{root_id}/spend-approval` records an explicit, durable zero-cost
  receipt bound to owner, approved plan revision, route policy, mode, currency, per-research
  bound, and exact ceiling cents. It returns the opaque authority digest and server-issued
  recovery session identity required to recover an ambiguous launch response.
- `POST /research/plans/{root_id}/launch` rejects a missing or stale digest and also requires
  the matching completed approval receipt. A matching hash without the receipt is not consent.
- `GET /research/sessions/{session_id}` returns integer-cent approved, authorized, observed,
  held, and available balances plus run state, breach state, and an opaque unknown-outcome
  count. Hard sessions are owner-scoped before any research or financial state is returned.
- `POST /research/sessions/{session_id}/spend/reconcile` refreshes authoritative evidence.
  It never retries provider work or releases a hold from a local transport guess.

Approval wording:

> I approve a $X.XX hard authorized-spend ceiling for this exact plan.

Guarantee wording:

> This bounds spend Antiek authorizes. Taxes, currency conversion, external fees, and
> provider misbilling are outside the guarantee and remain visible as breaches.

## Invariant trace

1. The server projector classifies every reachable hard-mode route. Unknown, stale,
   non-USD, unbounded, non-idempotent, non-reconcilable, or hidden-retry paths are ineligible.
2. Explicit approval creates the run and a completed durable approval receipt.
3. Launch recomputes the exact authority from current server state and verifies both digest
   and receipt before creating the launch receipt or dispatching work.
4. Paid gateway tests prove reserve-before-send, one send marker per operation, exact-headroom
   concurrency, retained ambiguous holds, provider-evidence-only settlement, and visible breach.
5. Session status reads owner-scoped ledger snapshots. Automatic polling backs off and stops
   after three terminal unresolved checks; held cents stay visible and the operator can request
   another provider-status check without retrying work.

## Verification evidence

- Backend projection/API/gateway/ledger suite: `151 passed`.
- Focused React suites: `33 passed`.
- TypeScript typecheck: passed.
- Production Vite build: passed.
- Token, type-scale, and token-parity gates: passed.
- Desktop and 390px mobile Playwright: `2 passed`; no horizontal overflow. This browser test
  mocks the authoritative transport to prove UI state and interaction only. The non-mocked
  gateway/ledger suites prove reservation concurrency, provider sends, restart, and breach.
- Axe on the hard-ceiling evidence region: zero serious or critical violations.
- Changed Python modules: Ruff passed; strict mypy passed.

Broad local-suite caveats, both unrelated to this diff:

- A clean `npm test` inherits an invalid Node `--localstorage-file` configuration and fails
  existing localStorage/hotkey/notebook tests before product assertions. Focused suites and
  hosted Vitest remain the release gates.
- Declared mypy in the minimal local environment reports existing optional scientific imports
  as absent. Strict mypy over every changed Python module passes; hosted declared mypy remains
  the release gate.

## Files

- API and ledger: `interfaces/research/api/cascade_routes.py`,
  `substrate/research_spend/ledger.py`
- Projection authority: `runtime/research_runner/cost_projection.py`,
  `runtime/research_runner/provider_gateway.py`, `dispatch_inventory.json`
- Client and approval UI: `apps/reading/src/api/research.ts`,
  `ResearchWorkstation/CascadeProposal.tsx`
- Live evidence UI: `DeepResearchWorkspace/HardCeilingEvidence.tsx`,
  `useResearchSession.ts`, `index.tsx`
- Browser proof: `apps/reading/e2e/research-hard-ceiling.spec.ts`
- Focused API, ledger, projection, component, and browser tests accompany each boundary.

Current capability boundary: the production hard path is intentionally available only for
manually supplied subquestions and zero-cost contract gather. Automatic decomposition and Exa
remain stop-limit-only until their complete paid routes are bounded, idempotent, and reconcilable.
