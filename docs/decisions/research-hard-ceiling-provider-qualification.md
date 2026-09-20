# Research hard-ceiling provider qualification

**Status:** Refused for all evaluated paid routes

**Checked:** 2026-07-13

**Contract:** `runtime/research_runner/provider_gateway.py`

## Decision

Keep Exa Agent, Tavily Research, Perplexity Agent, and OpenAI Responses out of
Antiek research hard-ceiling mode. They remain usable under the truthful stop
limit contract. A route can enter hard mode only when primary provider evidence
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

## Reversal conditions

Re-evaluate a route only when its current official contract or a signed
enterprise agreement provides a provider-enforced idempotency key on create and
authoritative lookup by that key. Refresh every matrix source, pin pricing and
expiry in the server catalog, implement one-send transport with retries disabled,
and fault-inject response loss before changing the verdict to `qualified`.
