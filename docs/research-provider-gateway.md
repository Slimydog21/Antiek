# Research provider gateway

SPR-03 joins the conservative projection contract to the durable spend ledger
at the last safe point before provider I/O. It does not claim that the current
Exa or LLM routes can enforce a hard ceiling. Those routes remain available in
legacy `stop_limit` mode and are rejected before construction in
`hard_ceiling` mode.

## Dispatch sequence

```mermaid
sequenceDiagram
    participant R as Research runner
    participant G as Provider gateway
    participant P as Cost projector
    participant L as Spend ledger
    participant A as Provider adapter
    R->>G: logical operation + exact run binding
    G->>P: bounded route request
    P-->>G: eligible maximum or refusal
    G->>L: reserve maximum (atomic)
    L-->>G: durable reserved hold
    G->>L: mark dispatch_possible
    L-->>G: durable send intent + provider key
    G->>A: send_once(operation, provider key)
    alt authoritative success
        A-->>G: actual cents + evidence
        G->>L: settle
    else definite not sent
        A-->>G: ProviderNotSent + evidence
        G->>L: authoritative release
    else timeout or ambiguous exception
        A--xG: outcome unavailable
        G->>L: mark unknown; retain full hold
    end
```

On replay, `reserved` means the send marker never committed and can be
released as provably unsent. `dispatch_possible` and `unknown` are never sent
again; the adapter must reconcile the persisted provider idempotency key.
`settled` and `released` are terminal replays.

## Failure matrix

| Interruption | Durable state | Allowed recovery | Blind send? |
|---|---|---|---|
| Before projection or refusal | none | Correct request or select `stop_limit` | No |
| After projection, before reserve | none | Re-project from server catalog | No |
| During atomic reserve | absent or `reserved` | Replay reserve command | No |
| After reserve, before send marker | `reserved` | Release, or resume within the same live attempt | No |
| After send marker, before adapter call | `dispatch_possible` | Authoritative provider lookup; not-found may release | No |
| During send / response lost | `unknown` | Authoritative provider lookup | No |
| Provider returned, process died before settle | `dispatch_possible` | Lookup actual billing and settle | No |
| Actual exceeds projected maximum | `settled`, run `ceiling_breached` | Preserve observed excess; reject new work | No |
| Execution closes with ambiguity | `closed_unresolved` | Evidence-only reconciliation | No |
| Last hold resolves after close | `closed_reconciled` | None | No |

An ordinary transport exception is never evidence that bytes were not
accepted. Only `ProviderNotSent` with adapter evidence or an authoritative
reconciliation result of `not_found` releases a post-marker hold.

## Provider capability table

| Seam | Current hard-mode status | Reason |
|---|---|---|
| Session launch | Receipted zero-cost | Durable completion distinguishes a launched session from an interrupted setup |
| Plan decomposer | Refused | Router fallback attempts have no durable provider identity or billing lookup |
| Contract gather stub | Receipted zero-cost | Local deterministic fixture; no provider/network dispatch |
| Exa search | Refused | Estimate is not invoice authority; client retries; no idempotency/reconciliation contract |
| Origin URL fetch | Unreachable | Only reached below the refused Exa gather branch in the cascade path |
| Local embedding bootstrap | Receipted zero-cost | Contract-stub note promotion reaches it; local inference is unmetered |
| Synthesis tail | Skipped | Parse repair plus provider fallback can multiply physical sends |
| Knowledge extraction | Unreachable | It is below the skipped synthesis tail and can multiply domain/repair/fallback sends |

A future eligible adapter must pin provider and model, accept a durable
idempotency key, disable SDK retries, and return authoritative status plus
billing evidence for that key. Pricing and capability authority remain in the
server catalog, not in the adapter or request.

## Authority binding

Hard-mode launch binds the ledger run to owner, deterministic session/root,
the complete approved plan tree, approval revision, launch budgets, exact
approved ceiling, gather mode, synthesis disposition, and USD. Any plan edit,
approval revision, owner, route, or ceiling change derives a new digest and run
identity. The ledger rejects reuse with changed authority.

Plan creation persists whether decomposition came from explicit caller-supplied
sub-questions or the automatic dispatch decomposer. Hard mode fails closed
unless that provenance records explicit sub-questions and the resulting tree
was subsequently approved. Creating a plan in `stop_limit` mode cannot make an
earlier unledgered decomposition eligible for a later hard-mode launch.

An identical launch after process restart replays only when the bound ledger run
also has a completed session-launch receipt. It returns the deterministic
session and leaf identities with `replayed: true`; durable session status
remains reconstructable from the research event log. A prepared launch receipt
means setup was interrupted and returns an explicit recovery conflict instead
of rerunning work or reporting a launch that did not happen.

## Inventory and bypass posture

`runtime/research_runner/dispatch_inventory.json` is paired one-for-one with
`HARD_MODE_DISPATCH_POLICY`. The test suite fails if either gains or loses a
seam without an explicit disposition. Hard mode currently has one reachable
execution path: session launch, the contract gather stub, and embedding
bootstrap, each wrapped in a durable zero-cost receipt. Automatic decomposition and Exa construction are rejected before
their direct client/router calls become reachable. The configured synthesis
tail is skipped for a hard-mode session and surfaced in `blocked_stages`.

Authenticated middleware identity supplies the run owner. Auth-disabled local
mode must opt in with `ANTIEK_ALLOW_LOCAL_HARD_CEILING=1`; this prevents an
accidentally exposed, unauthenticated deployment from authorizing spend.

`stop_limit` remains intentionally distinct: it preserves the existing
reported-cost runner behavior and provider routes. It is a useful operational
limit, not a pre-dispatch billing guarantee.
