# Krea scene-art substrate (Mountain Shell SPR-02)

The secure, budgeted, cacheable, **offline-safe** plumbing the living
mountain background (SPR-04) depends on. SPR-04 consumes the `useKreaScene`
hook and never touches the network plumbing or the key directly.

> **Honesty label.** The Krea wire shapes (`/generate/image/{model_path}`,
> `/jobs/{id}`) are **docs-current as of 2026-06-12** (transcribed from
> docs.krea.ai; the API launched in its current form 2026-05-27) — **live
> verification is pending the SPR-09 capped smoke**; no live Krea call has
> ever been made from this codebase. The *frontend contract* below (the hook
> shape + the `/krea/scene` 200/503 shapes) is what this code is built
> against and is stable regardless of the live Krea schema. If the live
> schema differs, only `_submit_generation` / `_poll_job` in
> `interfaces/research/api/krea_routes.py` change.

## The contract SPR-04 builds against (the seam)

```ts
import { useKreaScene } from "../krea/useKreaScene";

const { status, art, error, isFallback } = useKreaScene({
  mood: "calm", dayNight: "day", season: "summer",
});
```

Return shape (`UseKreaScene`):

| field        | type                                          | meaning |
|--------------|-----------------------------------------------|---------|
| `status`     | `"idle" \| "loading" \| "ready" \| "fallback"` | lifecycle |
| `art`        | `KreaArt \| null`                              | `{ image_url, scene_key, cached }` — **always non-null after first resolve**: live URL when `ready`, deterministic placeholder when `fallback` |
| `error`      | `string \| null`                               | honest reason when fallback (e.g. `"no_key"`, `"over_daily_budget"`); `null` when ready |
| `isFallback` | `boolean`                                      | `true` ⇒ `art.image_url` is the deterministic placeholder |

**Guarantees** (SPR-04 may rely on these):
1. **Never throws.** Disabled / over-budget / offline / any upstream failure
   → `isFallback: true` + a deterministic placeholder.
2. **Deterministic placeholder.** The same scene-state always yields the
   byte-identical data-URI (no `Date.now`, no `Math.random`) → SPR-04
   snapshots are stable.
3. `art` is always non-null after the first resolve, so the background always
   has something to paint.

## `/krea/scene` request/response (the proxy contract)

```
GET /krea/scene?mood=calm&day_night=day&season=summer

200 (SceneArt):
  { "enabled": true, "isFallback": false,
    "image_url": "https://...", "scene_key": "calm|day|summer",
    "cached": false }

503 (DisabledResponse — the FALLBACK signal, for EVERY failure mode):
  { "enabled": false, "isFallback": true,
    "reason": "no_key" | "kill_switch" | "over_daily_budget" |
              "rate_limited" | "upstream_error" | "upstream_timeout" |
              "upstream_bad_response" | "job_failed" | "job_timeout" |
              "job_cancelled" | "no_api_balance",
    "scene_key": "calm|day|summer" | null }
```

The `reason` vocabulary is **additive-only** (existing strings never change).
The two newest reasons (added 2026-06-12, SPR-01):

- `job_cancelled` — the job reached Krea's terminal `cancelled` state
  (one of the 9 documented job states; polling stops immediately).
- `no_api_balance` — upstream HTTP 402: Krea's **prepaid API balance**
  (separate from any web subscription; $5 minimum top-up) is empty. The
  operator's signal to top up — distinct from our local `over_daily_budget`.

The lower-level `POST /krea/generate` (submit → `{job_id,status}`; prompt
≤ 1800 chars, width/height 512–2368 px per the flux-1-dev contract —
out-of-bounds gets a 422 naming the bound) and `GET /krea/jobs/{id}` (poll →
`{status,image_url?,error_code?}`) exist too; SPR-04 normally uses
`/krea/scene`, which encapsulates prompt + submit + poll + cache + budget
behind one GET.

## The test-time mock (run SPR-04 + CI with ZERO network)

`src/krea/__mocks__/useKreaScene.ts` is a drop-in fake exposing the same
contract, always returning the deterministic placeholder:

```ts
// auto-mock (vitest resolves the __mocks__ sibling):
vi.mock("../krea/useKreaScene");

// or import the fake directly:
import { useKreaScene } from "../krea/__mocks__/useKreaScene";

// to exercise the live-art branch deterministically:
import { mockReadyScene } from "../krea/__mocks__/useKreaScene";
const fakeHook = mockReadyScene("https://img/fixed.png");
```

## Where things live

| file | role |
|------|------|
| `interfaces/research/api/krea_routes.py` | backend proxy: holds the server-side Krea bearer-token env var, budget + rate limit + kill-switch + TTL cache, doc-derived Krea adapters |
| `src/api/krea.ts` | typed client (`requestScene` / `generateImage` / `getJob`); talks only to `/krea/*`, never a key |
| `src/krea/useKreaScene.ts` | the React hook + pure `resolveScene` test seam |
| `src/krea/placeholder.ts` | deterministic offline placeholder + `sceneKeyOf` |
| `src/krea/__mocks__/useKreaScene.ts` | offline mock for SPR-04 + CI |

## Budget defaults (server-side; every number derived)

Pricing (docs.krea.ai, 2026-06-12): **flux-1-dev is $0.007/request**, drawn
from a **prepaid API balance** ($5 minimum top-up; **the API has NO free
tier** — the balance is separate from any web subscription's compute units;
upstream answers HTTP 402 → `no_api_balance` when it's empty).

- **Daily cap** `KREA_DAILY_UNIT_CAP=50` — 50 requests × $0.007 ≈
  **$0.35/day** worst case (~$10.50/mo); a $5 minimum top-up survives ≥14
  maxed-out days.
- **Rate limit** `KREA_RATE_LIMIT_MAX=6` per 60s — generation takes seconds
  (Krea-2 is documented ~10s; flux-1-dev undocumented), so ~6/min is
  generous for one operator yet caps a runaway loop.
- **Poll budget** `KREA_POLL_BUDGET_S=30` — 3× the documented Krea-2 ~10s
  (flux-1-dev latency is undocumented), well under Krea's 3-minute hosted
  job timeout. Poll cadence is 2.5s, inside the documented 2–5s guidance.
- **Cache TTL** `KREA_CACHE_TTL_S=3600` — a scene-state is stable for long
  stretches; 1h de-bills a session's repeats.
- **Model path** `ANTIEK_KREA_MODEL_PATH=bfl/flux-1-dev` — the model is a
  URL path segment per the docs, never a body field; swap models here.
- **Kill-switch** `KREA_KILL_SWITCH=1` — forces fallback regardless of key.

**Billing-accounting divergence (deliberate, 2026-06-12).** Krea bills on
job **completion** and does not bill failed/cancelled jobs; the proxy's
daily counter instead records a unit on **any 2xx submit answer, before the
body is parsed**. So the local count OVERCOUNTS on jobs that later fail —
the safe direction for a runaway guard (the proxy throttles itself before
the prepaid balance drains, never the reverse). Revisit only if the cap
starts starving legitimate use under a high upstream failure rate — and fix
it by reconciling against Krea's billing, not by loosening the
record-before-parse ordering.

Defaults are conservative; the operator tunes via env (no restart needed —
read at call time). See `apps/reading/.env.example` for the backend env
documentation. The cache + budget are **in-memory** (process-local dict);
they touch **no DuckDB and no db_lock** — the single-writer invariant is
untouched.

## Fallback visibility (antiek-living-caliber SPR-04)

The proxy collapses **every** failure into a typed 503 + a deterministic
procedural placeholder, so the background degrades **seamlessly** — which is
exactly why the product could serve fallback art *forever with zero signal*.
SPR-04 gives that degradation a **voice** without touching its guarantees: the
typed-503 contract above is **sacred** (observe it, never redesign it). Three
surfaces, in increasing depth.

### The log/response split (the load-bearing rule)

When a 503 is minted, the sanitized ≤300-char upstream **preview** goes to the
**logs and the failure ring — NEVER to the response body**. The 503 body stays
exactly `{enabled, isFallback, reason, scene_key}` (no `preview`, no `detail`).
This is deliberate: the preview can carry upstream prose that may echo our auth
header back, so it must not reach the browser. **Defence by construction:** the
preview is run through a token-pattern scrubber (`_scrub_secrets`) **before** it
is stored or logged, so no credential-shaped substring (a `Bearer …` header, an
`sk-…` key, a `token=`/`secret`/`apikey`/`password` field) survives onto **any**
channel. Planted-fake-token tests assert zero token material on the status
payload, the ring buffer, **and** every log record.

The WARNING line (one per minted 503, on the `antiek.interfaces.krea` logger):

```
WARNING antiek.interfaces.krea: krea fallback: reason=no_api_balance scene_key=calm|day|summer preview=<sanitized ≤300 chars>
```

These WARNINGs are the **durable** tier: the systemd journal persists them
across restarts. The in-memory ring (below) is the **live** tier — fast,
process-local, last-50, **emptied on restart** (no DuckDB / event-log; the
single-writer invariant is untouched — the journal is the cross-restart trail).

### `GET /krea/status` — the operator pull surface

Operator-auth only (it is **not** in `app.py`'s `_OPERATOR_AUTH_OPEN_PATHS`, so
the operator-auth middleware gates it like any other path — **401 without
operator creds**). Read-only: repeated calls perturb no budget / rate / cache
counter. `key_present` is a **boolean only** — it never carries token material.

```jsonc
GET /krea/status            // operator-auth required (401 without creds)

200 (no-key posture):
{
  "enabled": false,                 // key_present AND not kill_switch
  "key_present": false,             // BOOLEAN only — never token bytes
  "kill_switch": false,
  "gate_verdict": "no_key",         // what /krea/scene would do now; the
                                    //   first gate that trips (kill_switch →
                                    //   no_key → over_daily_budget →
                                    //   rate_limited); null ⇒ would generate
  "budget":      { "spent_today": 0, "cap": 50 },
  "rate_window": { "occupancy": 0, "max": 6, "window_s": 60.0 },
  "cache":       { "entries": 0, "hits": 0, "misses": 0 },
  "last_success_at": null,          // ISO-8601 of the last LIVE generation
  "failure_counts": {},             // total failures by reason (NOT ring-bounded)
  "failures": []                    // the last ≤50 sanitized ring entries
}
```

A populated ring entry (the sanitized `preview` is never the raw upstream prose):

```jsonc
{
  "timestamp": "2026-06-13T18:00:00+00:00",  // UTC ISO-8601
  "reason": "over_daily_budget",
  "scene_key": "calm|day|summer",            // null when not a /krea/scene call
  "preview": ""                              // sanitized ≤300 chars (empty for
                                             //   gate rejects with no upstream prose)
}
```

### The operator fallback badge — the always-on glance

`src/scene/SceneStatusBadge.tsx`, mounted via `KreaArtLayer.tsx` + threaded
from `useSceneArt.ts` (`isFallback` + `reason`). It consumes **only** the
existing hook state — **no new network call** (it does not hit `/krea/status`).
The rule (auth IS the operator signal; single-operator product):

| viewer | art state | badge |
|--------|-----------|-------|
| operator (authenticated) | fallback | **present** — e.g. `scene: procedural · no_api_balance` |
| operator (authenticated) | live     | absent |
| non-operator (logged out / loading) | fallback | **absent from the DOM** (not CSS-hidden) |

A logged-out reader never sees an internal degradation reason — the badge node
is simply not rendered.

### The SPR-09 diagnostic ladder

When the live smoke (SPR-09) finds the scene on fallback, climb the rungs —
each reveals **more** but costs **more access**, and each has a hard limit:

1. **Badge** (in-app, operator glance) — *reveals:* that art is falling back +
   the single current reason. *Cannot:* show history, counts, budget, or which
   gate would trip next; it reflects only the latest hook resolve.
2. **`GET /krea/status`** (operator pull) — *reveals:* the live picture — the
   evaluated gate verdict, budget/rate/cache occupancy, per-reason failure
   counts, `last_success_at`, and the last ≤50 sanitized failures. *Cannot:*
   show history older than the ring (50) or anything from **before the last
   process restart** (the ring is in-memory), and the previews are **scrubbed**
   (no upstream secret prose, by design).
3. **Logs / systemd journal** (host access) — *reveals:* the **durable**,
   cross-restart WARNING trail with the sanitized preview per failure; survives
   restarts the ring does not. *Cannot:* reveal raw secret material (the same
   scrub ran before logging) and is still **sanitized** prose, not the verbatim
   upstream body.
4. **Direct `curl` against Krea** (operator, real key) — *reveals:* the
   **verbatim** upstream behaviour (the actual 401/402/5xx body, real latency)
   that the proxy deliberately sanitizes away. *Cannot:* be done from the
   browser or without the operator's real key — and is the **only** rung that
   sees unredacted upstream prose, which is why it sits last.

> **Amendment note (the log/response split, SPR-04).** The split — preview in
> the logs + ring, *never* in the response — is load-bearing: it is what lets
> the operator diagnose a degradation while guaranteeing the browser never
> receives upstream prose. Do not "helpfully" surface the preview in the 503
> body; that would reopen the leak this design closes.
