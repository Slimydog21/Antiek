# Research hard-ceiling provider qualification

**Status:** Refused for all evaluated paid routes

**Checked:** 2026-07-16

**Contract:** `runtime/research_runner/provider_gateway.py`

## Decision

Keep Exa Agent, Tavily Research, Perplexity Agent, OpenAI Responses, and AWS
Bedrock async invocation out of Antiek research hard-ceiling mode. They remain
usable under the truthful stop-limit contract. A route can enter hard mode only
when primary provider evidence
proves all five requirements:

1. pinned authoritative pricing for every bounded billing unit;
2. a caller-supplied idempotency key enforced durably by the provider;
3. disabled hidden client retries for the billable create operation;
4. authoritative lookup by that same key returning charged cost or authoritative
   not-found; and
5. stable provider evidence suitable for settlement.

The machine-readable source of truth is
`runtime/research_runner/provider_qualification.json`. The checked-in cost
catalog cannot claim all hard-ceiling capabilities for a paid route unless an
exact provider/model/operation record has a `qualified` verdict and five passing
dimensions.

## Evidence matrix

| Candidate route | Pricing | Durable idempotency | Retry control | Reconciliation | Stable evidence | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Exa Agent fixed effort | Pass | Unproven | Unproven | Fail | Pass | Refused |
| Tavily Research | Pass | Unproven | Unproven | Fail | Pass | Refused |
| Perplexity Agent | Pass | Unproven | Unproven | Fail | Pass | Refused |
| OpenAI Responses deep research | Pass | Unproven | Pass | Fail | Pass | Refused |
| AWS Bedrock StartAsyncInvoke | Unproven | Pass | Pass | Fail | Unproven | Refused |

Primary contracts checked:

- Exa publishes fixed-effort request pricing and retrievable run cost, but its
  create contract returns the run ID after acceptance and documents no
  caller-supplied idempotency key. Its `budget.maxCostDollars` field is currently
  documented as ignored. See [Agent overview](https://exa.ai/docs/reference/agent-api/overview),
  [create run](https://exa.ai/docs/reference/agent-api/create-a-run), and
  [get run](https://exa.ai/docs/reference/agent-api/get-a-run).
- Tavily publishes research credit boundaries and returns a task ID, but task
  retrieval requires that provider-generated ID and `/usage` is aggregate.
  See [credits and pricing](https://docs.tavily.com/documentation/api-credits),
  [create research](https://docs.tavily.com/documentation/api-reference/endpoint/research),
  [get research](https://docs.tavily.com/documentation/api-reference/endpoint/research-get),
  and [usage](https://docs.tavily.com/documentation/api-reference/endpoint/usage).
- Perplexity returns an exact USD cost breakdown for a stored Agent response,
  but the create contract documents no caller-enforced idempotency key or lookup
  by one. See [Agent create](https://docs.perplexity.ai/api-reference/agent-post)
  and [pricing](https://docs.perplexity.ai/docs/getting-started/pricing).
- OpenAI permits SDK retries to be disabled and background Responses to be
  retrieved by provider ID. `X-Client-Request-Id` is tracing/support identity,
  not documented deduplication or reconciliation identity. See
  [request IDs](https://platform.openai.com/docs/api-reference/introduction),
  [background mode](https://developers.openai.com/api/docs/guides/background),
  [pricing](https://developers.openai.com/api/docs/pricing), and
  [SDK retries](https://github.com/openai/openai-python#retries).
- AWS Bedrock `StartAsyncInvoke` has the strongest direct-provider identity contract
  evaluated so far: it accepts a durable `clientRequestToken`, and AWS SDKs can
  set maximum attempts to one. Its generic route does not pin one exact model,
  region, currency snapshot, or complete billing-unit set. `ListAsyncInvokes` returns tokens but cannot
  filter by one and documents no complete-retention boundary; `GetAsyncInvoke`
  requires the generated invocation ARN and does not return exact charge cents.
  A lost create response therefore cannot be reconciled into charged or
  authoritative not-found from Antiek's key. See
  [StartAsyncInvoke](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_StartAsyncInvoke.html),
  [ListAsyncInvokes](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ListAsyncInvokes.html),
  [GetAsyncInvoke](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_GetAsyncInvoke.html),
  [retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html),
  and [pricing](https://aws.amazon.com/bedrock/pricing/).

## Decisive failure trace

1. Antiek atomically reserves the maximum and persists `dispatch_possible`.
2. The provider accepts and may bill the create request.
3. The response carrying the provider-generated operation ID is lost.
4. Recovery has only Antiek's deterministic key. The provider's retrieve API
   requires the unknown provider ID.
5. Retrying may create and bill a second operation. Releasing the hold may hide
   the first charge. Aggregate usage cannot isolate this operation or prove
   authoritative not-found.
6. The only honest state is `unknown`, with the full hold retained indefinitely.

Callbacks, streaming an early generated ID, per-operation API keys, and account
usage deltas narrow or move the ambiguity window; none makes create acceptance
and Antiek identity durable as one provider-enforced operation.

Bedrock's caller token closes duplicate acceptance but not lookup. Scanning an
unfiltered paginated list is not authoritative not-found without a provider
guarantee that the list is complete for a bounded retention interval. Retrying
the create solely to recover the ARN would invoke a create operation from a
reconciliation-only path and is outside the gateway's no-send contract.

## Durable broker direction

The viable reversal is an Antiek-owned broker that durably commits the caller
key and bounded authorization before any upstream call, exposes exact lookup by
that key, performs one upstream send with SDK retries disabled, and persists the
upstream identity and terminal charge evidence. The broker, rather than an
unverifiable external create response, becomes Antiek's qualified provider
boundary. It must absorb upstream ambiguity without releasing the user's hold,
never claim authoritative not-found after an upstream send marker, and pass
crash injection at every persistence/network boundary. The executable contract
is specified in `docs/htmlspec/antiek-durable-provider-broker.html`; it does not
qualify any route by itself.

## Reversal conditions

Re-evaluate a route only when its current official contract or a signed
enterprise agreement provides a provider-enforced idempotency key on create and
authoritative lookup by that key. Refresh every matrix source, pin pricing and
expiry in the server catalog, implement one-send transport with retries disabled,
and fault-inject response loss before changing the verdict to `qualified`.
