# DRW plan failure contract (`POST /research/plans`)

Binding cross-stack contract for decompose failures on the Deep Research Workflow
plan endpoint. Backend (`interfaces/research/api/cascade_routes.py` `create_plan`)
and frontend (`apps/reading` DRW proposal flow) MUST implement this verbatim.

**Incident:** 2026-06-17 — every decompose failure rendered as “model provider isn't
configured” because `CascadeProposal.tsx` called `setFailed("")` and discarded the
502 body (`decompose_failed: {type}: {exc}`).

Anchors: `cascade_routes.py:272-288`, `CascadeProposal.tsx:117-125`,
`substrate/dispatch/router.py:537-544`, `substrate/dispatch/base.py:29-49`.

---

## 1. Closed code set (exactly five)

| Code | Meaning |
|------|---------|
| `provider_unconfigured` | No LLM provider registered; dispatch chain exhausted with `provider=None` on every tier. |
| `provider_upstream_error` | A configured provider was invoked and returned a dispatch failure (`ProviderError` with a real provider/model). |
| `timeout` | Decompose exceeded time (`asyncio.TimeoutError` or `TimeoutError`). |
| `backend_unreachable` | **Client-only:** the browser could not complete HTTP to the API (fetch threw; not an `ApiError`). |
| `unknown` | Any other exception during decompose — honest catch-all; never substitute a guessed cause. |

No sixth code without a new binding decision after an observed recurring failure.

---

## 2. Wire envelope (FastAPI)

Response body shape:

```json
{
  "detail": {
    "code": "<one of the five server codes>",
    "message": "<human-safe string>",
    "retryable": <bool>
  }
}
```

`backend_unreachable` is never emitted by the server.

**Examples**

`provider_unconfigured` (503):

```json
{
  "detail": {
    "code": "provider_unconfigured",
    "message": "No model provider is configured. Set a provider key and restart.",
    "retryable": false
  }
}
```

`provider_upstream_error` (502):

```json
{
  "detail": {
    "code": "provider_upstream_error",
    "message": "The model provider returned an error. Retry, or check your key's quota.",
    "retryable": true
  }
}
```

**Forbidden in `message`:** `type(exc).__name__`, tier names, model ids, stack
traces, `str(exc)` verbatim, or the substring `ProviderError`.

Server-side diagnostics belong in logs only (WARNING with type + message).

---

## 3. HTTP status map

| Code | HTTP status | Notes |
|------|-------------|-------|
| `provider_unconfigured` | 503 | Service unavailable for AI decompose |
| `provider_upstream_error` | 502 | Bad gateway / upstream provider failure |
| `timeout` | 504 | Gateway timeout |
| `unknown` | 500 | Unexpected server error |
| `backend_unreachable` | *(none)* | Client-only; fetch layer |

---

## 4. Canonical per-code copy (frontend must match exactly)

| code | headline (verbatim) | retry? |
|------|---------------------|--------|
| `backend_unreachable` | The research engine isn't running. Start the backend, then retry. | yes |
| `provider_unconfigured` | No model provider is configured. Set a provider key and restart. | no |
| `provider_upstream_error` | The model provider returned an error. Retry, or check your key's quota. | yes |
| `timeout` | The engine took too long to respond. Try again. | yes |
| `unknown` | Something unexpected went wrong. Try again. | yes |

`retry?` column defines the default `retryable` the backend sets and the UI uses
to show or hide “Try again.”

The `unknown` row is the honest catch-all: do not relabel it as a provider or
network issue when the code is not `unknown`.

For `unknown` only, the UI may also show a safe engine `reason` string in the
existing “Engine:” affordance when one exists — without asserting a specific cause.

---

## 5. Classification rules (exception → code)

Implement in `classify_dispatch_failure(exc)` (pure function).

1. **`provider_unconfigured`** — `ProviderError` where `exc.provider == "<none>"`
   (router `router.py:539-543` when every tier has `provider=None`), **or** the
   message indicates the tier is not bootstrapped (`not registered`, `no API key`,
   per `router.py:444-448` when the registry is empty but the chain names a provider).

2. **`provider_upstream_error`** — any other `ProviderError` with a real
   `provider` / `model` (not `"<none>"`). Set `retryable` from `exc.retryable`
   (default `True` if absent).

3. **`timeout`** — `asyncio.TimeoutError` or builtin `TimeoutError`.

4. **`unknown`** — all other exceptions. **Never** map non-provider exceptions
   to `provider_unconfigured`.

5. **`backend_unreachable`** — classified only in the frontend when `fetch` fails
   without an `ApiError` (network down, CORS preflight failure, connection refused).

**Edge cases**

| Situation | Code |
|-----------|------|
| `ValueError` from `build_plan` / persistence | `unknown` |
| `ProviderError(retryable=True)` with `provider="<none>"` | `provider_unconfigured` |
| Partial registry (some tiers up, decomposer tier down) | `provider_upstream_error` or `provider_unconfigured` per the raised `ProviderError` — do not pre-gate the route |
| Unparseable HTTP error body on client | `unknown` |

---

## 6. Boot / health honesty

When zero providers register at startup: log one actionable WARNING (do not crash).
`/health` exposes `providers_ready: bool` where `providers_ready = len(registered_providers) > 0`.

---

## 7. Rejected alternative (steelman)

Showing raw `decompose_failed: ProviderError: …` in the UI is maximally transparent
for developers and needs no mapping table. It leaks internal type names, tier/model
identifiers, and provider errors to operators who cannot act on them, and it trains
the product to sound like a stack trace. This contract hides internals in `message`
while preserving them in server logs.

---

## 8. Why five codes, why `detail`

Four codes would collapse distinct operator actions (restart backend vs configure keys
vs retry vs wait). Six codes without observed recurrence invites speculative taxonomy.
The envelope lives under FastAPI’s conventional `detail` field, matching existing
422 patterns in `app.py` and what `apiFetch` already surfaces as response text.