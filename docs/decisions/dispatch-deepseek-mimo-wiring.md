# Dispatch — DeepSeek V4 Pro + MiMo V2.5 Pro via API, not self-host

**Decision date:** 2026-05-27 (SPR-01, Living Roadmap run)
**Status:** ✅ Built + mock-verified in CI; live-on-prod is operator-bound
(needs real provider keys set in the deploy env).
**Owner:** SPR-01 (turning the AI on — wiring the Ask path through Hermes).
**Invariant context:** CLAUDE.md §16 (dispatch is Hermes-primary, no
self-hosted LLMs, no second runtime) + `docs/decisions/substrate_dispatch_boundary.md`.

## The decision

Register **DeepSeek V4 Pro** and **Xiaomi MiMo V2.5 Pro** as
OpenAI-compatible providers behind the existing dispatch router, consumed
through their **hosted APIs**. The curated research-entry tier resolves
"deep" → DeepSeek V4 Pro and "fast" → MiMo V2.5 Pro. We do **not**
self-host either model, and we do **not** add a second runtime/dispatcher.

Both providers reuse the one `OpenAICompatProvider` adapter
(`substrate/dispatch/providers/openai_compat.py`) — a direct mirror of the
existing xAI/Grok bridge, which is itself registered as the OpenAI-compat
`hermes` provider in `substrate/dispatch/providers/bootstrap.py`
(`_maybe_hermes`, the `api.x.ai`/Hermes-served-Grok bridge with the
`chat_completions_path="/chat/completions"` + OAuth-refresh→503 posture).
No parallel adapter was invented.

## Why API, not self-host

1. **Cost at single-operator volume.** Self-hosting a frontier-class model
   on rented GPUs costs roughly **100–1000×** more per token than the
   hosted API at the volume one operator generates. A reserved GPU bills
   24/7 whether or not a request is in flight; the API bills per token. The
   substrate's quality thesis is that the moat comes from **volume of
   dispatches over a compounding graph** (`substrate/dispatch/config.yaml`
   architectural posture), not from owning the weights — so paying a fixed
   GPU rent to serve a bursty single-operator workload is strictly worse
   economics.
2. **Stable endpoint vs preemptible GPUs.** The only GPUs available to this
   project are **preemptible/spot-class** (per the §16 REJECT line on
   Modal/Daytona as dispatch providers). A preemptible instance cannot hold
   a stable inference endpoint — it can be reclaimed mid-request — so a
   self-hosted model would need a fallback to a hosted API anyway. The
   hosted API IS that stable endpoint; adding a self-host layer in front of
   it is pure complexity with no availability gain.
3. **Both models already have cheap APIs Hermes-style dispatch calls.**
   DeepSeek and MiMo both expose OpenAI-shaped chat-completions endpoints.
   The router already speaks that shape (one adapter, several providers).
   Wiring them is a config + bootstrap edit, not new infrastructure.
4. **§16 + the substrate/dispatch boundary.** Dispatch is Hermes-primary
   and vendor-pluggable; vendor SDKs live only in
   `substrate/dispatch/providers/`. Self-hosting would introduce a serving
   runtime (a second dispatcher) that §16 explicitly rejects and that the
   boundary lint would not contain.

## Reconsider-if

Flip to (or add) a self-hosted path **only** if BOTH economics and
availability invert:

- **Sustained volume saturates multiple GPUs 24/7.** If dispatch volume
  grows to the point where reserved GPUs would run hot around the clock,
  the 100–1000× multiplier collapses and self-host amortizes. This is a
  multi-user / Sprint-22+ concern, not a single-operator one — and the
  measurement lives in the `dispatch.call` cost events the router already
  emits.
- **A hard data-residency / confidentiality ruling rules out every hosted
  API.** If a legal or contractual constraint forbids sending content to
  any third-party API (e.g. a publisher contract under the §9.0 legal
  gate), self-host becomes the only compliant option. Absent such a
  ruling, the hosted APIs are fine.

Either trigger is a **named** reconsider event, not a silent drift — and
even then the change is "add a `providers/` adapter behind the same router
+ a serving runtime decision," never a second dispatcher.

## The exact env vars (reproducible deploy)

Keys are read from NAMED env vars; never hardcoded. A provider registers
**only** when its key is present (degraded posture, not an error — see
`substrate/dispatch/providers/bootstrap.py` docstring + the keys-absent
test in `tests/test_research_tier_dispatch.py::test_keys_absent_registers_nothing`).

| Provider | Tier | Key env var | Base-URL override env var | Default base URL |
|---|---|---|---|---|
| DeepSeek V4 Pro | `deep` | `DEEPSEEK_API_KEY` | `ANTIEK_DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |
| Xiaomi MiMo V2.5 Pro | `fast` | `XIAOMI_API_KEY` | `ANTIEK_XIAOMI_BASE_URL` | `https://api.mimo.xiaomi.com/v1` |

The per-call **model ids** (`deepseek-v4-pro`, `mimo-v2.5-pro`) are NOT
pinned in bootstrap — one endpoint serves several models. They live in the
tier→provider map (`substrate/dispatch/research_tier.py`), the ONE place
the curated tier resolves to a concrete `(provider, model)`.

## Assumptions surfaced (honesty — verify on prod)

These are explicit assumptions, NOT claims of a verified live contract.
"Mock passed in CI" ≠ "a completion came back on prod" (the latter is
operator-bound — it needs real keys).

1. **MiMo base URL carries `/v1`.** The default `https://api.mimo.xiaomi.com/v1`
   already includes the version prefix, so MiMo is given the
   `chat_completions_path="/chat/completions"` override (matching the
   OpenRouter/Hermes pattern) to avoid the double-`/v1/v1/chat/completions`
   404 that the Hermes regression
   (`tests/test_dispatch_bootstrap.py::test_hermes_provider_url_does_not_double_v1`)
   documents. **If MiMo's real base omits `/v1`,** set
   `ANTIEK_XIAOMI_BASE_URL` to a URL that includes it; the path override
   stays correct as long as the base carries the prefix.
2. **Both speak OpenAI chat-completions verbatim.** DeepSeek and MiMo are
   assumed to return the standard `choices[0].message.content` +
   `usage.{prompt,completion}_tokens` shape the adapter parses. If either
   diverges (a different streaming envelope, a reasoning-token block, a
   tool-call field shape, or a cached-token field name other than the two
   `_extract_cached_tokens` already handles), the adapter raises
   `ProviderError("unexpected response shape")` rather than silently
   coercing — the divergence surfaces as a queryable failure, and the fix
   is to extend the adapter, not to claim "wired" over a coerced response.
3. **Model ids are guesses pending prod confirmation.** `deepseek-v4-pro`
   and `mimo-v2.5-pro` are the assumed model identifiers. The operator must
   confirm the exact strings against each provider's live model list and,
   if different, update them in `research_tier.py` (one edit, one place).

## How the selection actually changes the route (M3 mechanism)

The recorded tier is not just metadata — it changes which provider is
called, via a **per-call primary swap** on the one Hermes-routed dispatch
path (NOT a second dispatcher — §16 holds):

1. The operator's fast/deep choice rides on the start event
   (`InvestigationStartRequestedPayload.research_tier`) and is recorded +
   queryable (`GET /investigations/{id}.research_tier`).
2. The **synthesizer** bridge (the human-facing artifact role, where the
   fast/deep choice is most felt) reads that recorded tier off the start
   event, resolves it through `resolve_research_tier`, and passes the
   resulting `(provider, model)` to `dispatch(..., provider_override=,
   model_override=)`.
3. `dispatch`'s override swaps **only the primary tier's**
   `(provider, model)`, keeping the SAME fallback chain. So "deep" routes
   the synthesizer's primary to DeepSeek V4 Pro; "fast" routes it to MiMo
   V2.5 Pro. The override is a **preference that only takes effect when its
   provider is actually registered**: the synthesizer applies it ONLY if
   the resolved tier provider is in the live registry (`_research_tier_override`
   checks `_PROVIDER_REGISTRY`). If the tier's provider key isn't set, the
   synthesizer routes through the config's own primary + fallback unchanged
   — a research-tier choice never *displaces* a working config route with
   an absent provider, it only *adds* routing when its provider is live.
   (This also stops the schema default of "deep" from silently re-routing
   every run onto an absent DeepSeek key.) As a second line of defence, the
   router ALSO converts an unregistered-override `KeyError` into a
   fallback-triggering `ProviderError`, so even a direct override to a dead
   provider degrades gracefully rather than crashing.

**Scope of consumption (deliberate, reported honestly):** the override is
wired at the **synthesizer** only this sprint — the role where model
choice changes the artifact the operator reads. The other roles
(decomposer, evidence_retriever, connector, …) still route through
`config.yaml`'s Hermes-primary tiers regardless of the chosen research
tier. Extending consumption to those roles is a bounded next step (thread
the tier into each role-request payload or read it the same way the
synthesizer does); it was NOT done here to avoid expanding optionality
across the hot path for roles where fast-vs-deep has no demonstrated
operator-felt difference (rigor #2). The tier is recorded for ALL roles
(queryable), but only consumed by synthesis.

## Named failure modes (rigor — enumerated, even where out of scope here)

- **Missing key** → provider not registered; tier falls back through the
  router's fallback chain; if nothing is registered, the Ask path surfaces
  a terminal `investigation.failed` (the original bug's honest fix —
  `tests/test_investigation_endpoints.py::test_no_provider_surfaces_terminal_failure_not_hang`).
- **Key present but 401** → `OpenAICompatProvider` raises a non-retryable
  `ProviderError`; the router records a failed `dispatch.call` event and
  tries the fallback. (Live-only; mock-covered by the adapter's 401 test.)
- **Stream drops mid-trajectory** → the current adapter is non-streaming
  (one POST, one JSON body); a dropped connection maps to a retryable
  `ProviderError`. True token-streaming is a later concern (router is
  synchronous by design per `base.py`); OOS for SPR-01.
- **Tier maps to an unregistered provider** → guarded:
  `resolve_research_tier` only ever returns `xiaomi`/`deepseek`, and
  `tests/test_research_tier_dispatch.py::test_resolved_provider_matches_a_bootstrap_registerable_name`
  asserts both resolve to bootstrap-registerable names. If the operator
  sets only one key, the missing tier's provider is simply unregistered and
  the dispatch falls back per the router's chain.
