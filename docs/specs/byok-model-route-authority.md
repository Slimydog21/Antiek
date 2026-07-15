# BYOK model route authority

Status: executable follow-up to the Settings add-model foundation

Owner surface: Research, Reading, and Writing prompt composers

Security boundary: server-owned provider registry and budget policy

## Problem

Settings can securely register a user-supplied provider endpoint, model id, and
encrypted API key. Registration alone must not silently rewrite a production
dispatch tier. The remaining product gap is an explicit, per-prompt action that
grants one registered model route authority and records that decision.

Until this spec ships, the UI and API must say `registered`, not `ready`, for a
user provider with no active tier binding.

## Required behavior

1. Every prompt composer that can start paid model work exposes a server-derived
   model choice. The minimum first slice is Start Research; Reading highlight
   research and Writing generation follow through the same shared control.
2. The choice list comes from the authenticated server. A client may submit a
   provider id and model id, but the server accepts the pair only when it exactly
   matches an enabled user-model registry record whose BYOK credential metadata
   has `pipeline_kind=model_provider` and `account_handle=<record id>`.
3. The default remains the existing curated tier. Choosing a user model changes
   only that prompt's primary route through the existing `provider_override` and
   `model_override` seam. It does not mutate `config.yaml`, create a second
   dispatcher, or remove the curated fallback chain.
4. Before submission, the UI displays the chosen provider/model, pricing-known
   state, projected spend range, remaining configured budget, and whether the
   prompt would exceed the hard ceiling. Unknown pricing is visibly unknown,
   never `$0.00`.
5. The server repeats the budget check at execution time. Client-side projection
   is explanatory, not authorization. A hard-ceiling rejection makes no provider
   call and returns a typed, value-free error.
6. The investigation or generation start event records both the user-visible
   choice and the resolved provider/model route. Replay and audit must be able to
   distinguish a curated default, an explicit user choice, and fallback use.
7. Deleted, disabled, stale, or metadata-mismatched providers fail closed before
   dispatch. Error responses and events never contain API keys or untrusted
   upstream response bodies.

## API contract

- Extend the model inventory with `route_eligible`, `pricing_status`, and the
  exact registered `model_id`; do not overload today's tier-bound `ready` field.
- Add an optional structured `model_choice` to prompt-start requests:
  `{authority: "user_model", provider_id, model_id}`. Absence means the current
  curated-tier behavior.
- Resolve and validate the choice in one shared server function used by all
  prompt surfaces. It returns a typed route override plus audit metadata; callers
  never read the JSON sidecar or BYOK store directly.
- Reject unknown pairs, half-specified choices, changed credential bindings, and
  disabled records with 409 or 422 before any event claiming work began.

## Acceptance tests

- A registered provider appears in the picker but remains non-ready in the
  tier-bound inventory until explicitly selected for a prompt.
- Selecting it causes a mocked end-to-end dispatch to call that provider with the
  registry-owned model id and preserves the configured fallback.
- Submitting another record's model id, a deleted provider, a changed credential
  reference, or an unrelated BYOK credential makes zero outbound calls.
- The start event, dispatch event, and resulting artifact identify the requested
  and resolved routes without secret material.
- Unknown pricing and over-budget states are rendered honestly; the hard ceiling
  is enforced server-side under concurrent submissions.
- Start Research keyboard and screen-reader flows can choose, review, clear, and
  submit a model without losing the prompt.

## Deliberate non-goals

- No global "replace every Antiek model" switch.
- No client-authored base URL, key, or arbitrary model override on a prompt.
- No live validation call during Settings registration.
- No new dispatch runtime or provider-specific path outside the existing router.
