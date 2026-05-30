# arXiv rate governor — host-scoped (mechanical) vs multi-IP (operational)

**Decision date:** 2026-05-30 (SPR-09, arxiv-ingest, M1 rate governor);
**amended 2026-05-31 (SPR-09 round-2)** — the two PRIMARY egress paths were
wired through the governor (see "Round-2 correction" below);
**amended 2026-05-31 (SPR-09 round-3)** — the 4th, previously-ungoverned egress
(the export-SEARCH API in `client.py`) was wired through the governor and the
lint was redesigned to catch the dynamic-URL bypass (see "Round-3 correction");
**amended 2026-05-31 (SPR-09 round-4, the ROOT)** — governance was made
**host-based, not module-location-based**: a new fetch-boundary helper
`govern_if_arxiv(url, send)` routes any arXiv-HOST URL through the governor
wherever it is fetched, the lint was made **host-based** (scans the whole
acquisition tree, not just `acquisition/arxiv/`), and the guarantee is reframed
below as a HOST RULE rather than an enumerated list of N egress paths (the
enumeration kept being wrong — three adversarial passes each found one more).
**amended 2026-05-31 (SPR-09 round-5, the TRANSPORT-LAYER terminating fix)** —
the host rule was made to hold **PER-REQUEST across the entire redirect chain**:
`govern_if_arxiv` checked the host of the INITIAL url only, but every fetcher
uses `follow_redirects=True`, so a NON-arXiv URL that 302-redirects to
`arxiv.org/pdf/<id>` issued a real UNGOVERNED GET to arXiv. The fix governs each
hop via an httpx `request` event hook (`install_arxiv_request_hook` /
`arxiv_governed_client`) that fires for EVERY hop — initial OR a redirect — so an
arXiv host is governed by construction regardless of the initial URL. The
LLM-callable `substrate/graph/rlm_tools.py::fetch_url` (a `requests` fetcher, so
the httpx hook does not apply) was closed by following redirects manually with
per-hop `govern_if_arxiv`, and the lint scope was extended to `substrate/graph/`
(see "Round-5 correction" below).
**Status:** ✅ Implemented — `acquisition/arxiv/rate_governor.py`
(`ArxivRateGovernor` / `governed_request` / `govern_if_arxiv`) serializes the
throttle's critical section under an exclusive `fcntl.flock`; **every external
fetcher in the acquisition tree routes its send through `govern_if_arxiv` /
`governed_request`, so any arxiv.org / export.arxiv.org host — wherever it is
fetched — is governed by construction**; `tools/lint/rate_governor_check.py`
(host-based) reds ANY raw external HTTP fetcher in `acquisition/` that is not so
routed (URL-agnostic — a runtime-resolved arXiv URL can no longer slip past from
any module).
**Owner:** SPR-09 ToS-compliance guardrails, M1.
**Reuses:** `acquisition/arxiv/throttle.py::ArxivThrottle` (verbatim, never
re-implemented) + the `runtime/db_lock.py` flock pattern.

## THE MECHANICAL GUARANTEE (the host rule — read this first)

> **EVERY request hop to an `arxiv.org` / `export.arxiv.org` host (or any
> `*.arxiv.org` subdomain) — the INITIAL request OR any REDIRECT hop httpx
> follows — from ANYWHERE in the codebase, is governed by the host-global
> governor. The fetch-boundary helper `govern_if_arxiv(url, send)` governs the
> initial hop, and an httpx `request` event hook
> (`install_arxiv_request_hook` / `arxiv_governed_client`) governs every
> subsequent redirect hop on its OWN host. CI — the host-based
> `tools/lint/rate_governor_check.py` — reds any raw external HTTP fetcher in
> the acquisition tree (and in `substrate/graph/`) that does not so route.**

The decision rule is the URL's **host at each request hop**, evaluated at
runtime — NOT which directory the fetcher lives in, and NOT only the initial URL.
An arXiv hop is governed; a non-arXiv hop is fetched directly with its own
throttling untouched. This is why the guarantee no longer depends on enumerating
"the N arXiv egress paths" NOR on the initial host being arXiv: the host check
happens at EACH hop on the actual resolved URL, so a fetcher cannot evade the
governor by living outside `acquisition/arxiv/` (the round-1/2/3 misses) and a
non-arXiv URL that 302-redirects to `arxiv.org/pdf/<id>` (the round-4-residual /
round-5 hole) cannot reach arXiv ungoverned. A runtime-resolved URL (an OpenAlex
`best_oa_pdf_url` that turns out to be `arxiv.org/pdf/<id>`, or an `oa_url` landing
page that redirects there) is caught the moment that hop is issued.

**Per-hop reconciliation (governed exactly once, no double-wait, no deadlock).**
When the initial host is itself arXiv, the outer `govern_if_arxiv` →
`governed_request` governs that one initial hop and CLAIMS it (the
`_claim_initial_hop` handshake) so the per-hop hook SKIPS exactly that hop and
governs only the redirect hops. The governor flock is **re-entrant per thread**,
so a redirect hop's hook re-acquiring the flock from inside the outer `send()`
cannot self-deadlock. When the initial host is NON-arXiv, the outer boundary
calls `send()` directly (no claim) and the hook is the sole governor of any arXiv
redirect hop — this is the hole that was LIVE on the OA path.

The known governed fetch boundaries below are listed as **examples**, not as an
exhaustive count — the count is irrelevant under the host rule, and prior
"exhaustive counts" were each wrong by one.

## The problem

`ArxivThrottle` already enforces arXiv's "no more than one request every three
seconds" guidance plus a `banned_until` 429 sentinel, and persists both to a
shared JSON state file (`~/.antiek/arxiv_throttle.json`) so the state survives
*across separate process invocations*. But its read-modify-write of that state
is explicitly **unlocked / last-writer-wins** (`throttle.py` docstring lines
18-23, the I/O comment line 137). Two concurrent jobs on the same box — a harvest
plus an on-demand PDF fetch, or two shells — can each read the same
`last_request_at`, both compute `elapsed >= 3s`, and **both fire inside one 3s
window**, collectively breaching the ceiling that historically IP-banned the box
(`project_researchmaxx_arxiv.md`, 2026-05-17). There was also no single-connection
cap across jobs.

## The decision

Wrap the throttle's `wait_if_needed -> send -> note_response` critical section
in an exclusive cross-process `fcntl.flock` (the canonical Antiek serialization
mechanism — the same `LOCK_EX` + poll-to-deadline + stale-PID-cleanup +
release-on-close pattern as `runtime/db_lock.py::connect_write`). Every host
arXiv send routes through `ArxivRateGovernor.governed_request`. Because only one
job can hold the lock, only one job is ever inside the gate, which makes the
>= 3s spacing **and** the ban-sentinel write **host-global**, and gives the
"<= 1 arXiv request in-flight across all jobs" single-connection property for
free. We do NOT re-implement throttling — re-implementing rate-limiting is the
documented cause of the historical ban; we reuse `ArxivThrottle` as-is and only
add the flock around its critical section. `ArxivBanned` propagates unchanged.

Each arXiv send routes through the governor (directly via `governed_request`
where the host is statically arXiv, or via `govern_if_arxiv(url, send)` where the
host is only known at runtime), passing an `ArxivThrottle` over the canonical
`~/.antiek/arxiv_throttle.json` so the spacing/ban engine is reused verbatim while
the flock makes the gate host-global. **Known governed fetch boundaries (EXAMPLES,
not an exhaustive count — the host rule governs the rest by construction):**

- `acquisition/arxiv/oai_pmh.py::_fetch_page` → `export.arxiv.org/oai2` — the
  OAI-PMH ListRecords harvest, the **busiest** path. (`governed_request`)
- `acquisition/arxiv/pdf_fetch.py::fetch_pdf` → `arxiv.org/pdf/<id>` — SPR-04's
  on-demand PDF fetch. (`governed_request`)
- `acquisition/arxiv/adapter._default_fetch_pdf` → `arxiv.org/pdf/<id>` — the
  fallback PDF fetcher. (`governed_request`)
- `acquisition/arxiv/client._http_get` → `export.arxiv.org/api/query` — the
  **export SEARCH API**, the endpoint named in the diligence-of-record as the one
  that historically IP-banned the box. (`governed_request`)
- `acquisition/openaccess/unpaywall.py::download_pdf` → an OpenAlex
  `best_oa_pdf_url` that, for an arXiv-mirrored work, is `arxiv.org/pdf/<id>` — the
  **round-4 root finding**: a fetcher OUTSIDE `acquisition/arxiv/` that resolves to
  an arXiv host at runtime, previously under the OA throttle (5 req/s, no flock, no
  ban sentinel), concurrency-blind to the harvest. Now routed through
  `govern_if_arxiv(pdf_url, send)`. (host-based)
- The remaining acquisition fetchers — `openaccess/pmc.py`, `openaccess/doaj.py`,
  `openaccess/openalex.py`, `urls/client.py`, `podcasts/client.py`,
  `voice/client.py`, `search/exa/client.py`, `books/public_domain.py` — all route
  their send through `govern_if_arxiv` too. For their normal non-arXiv hosts this
  is a no-op (the send is issued directly, their own throttling untouched); were
  any to resolve to an arXiv host it would be governed. This is the point of the
  host rule: governance is uniform and by-construction, not an allowlist of named
  paths. (host-based)

**Non-arXiv hosts keep their own throttling.** `govern_if_arxiv` only adds the
arXiv flock when the URL is an arXiv host; for the publisher / PMC / OpenAlex /
Gutenberg / archive.org hosts these fetchers normally hit, it calls `send()`
directly — the OA `OAThrottle` and the public-domain `SourceClient` throttle are
unchanged. There is no false governance (no spurious arXiv-flock contention) of
non-arXiv egress.

## Round-2 correction (the honesty record)

The initial SPR-09 round-1 landing routed ONLY the fallback
`adapter._default_fetch_pdf` through `governed_request`. The two **primary,
highest-volume** paths — `oai_pmh.py` (the harvest) and `pdf_fetch.py` (the
on-demand fetch) — still called the **bare unlocked** `throttle.request(send)`,
so two concurrent host jobs (a harvest + a PDF fetch, or two harvests) could
each read the same `last_request_at` and **both fire inside one 3s window** — the
exact un-spaced-parallel-stream race that historically IP-banned the box. The
round-1 governor tests were green only because they exercised the governor in
**isolation**, never the real callers. SPR-09 round-2 wired both primary callers
through `governed_request` and added **caller-level** tests
(`tests/test_rate_governor.py`) that drive the real `OaiPmhHarvester` /
`fetch_pdf` and prove the send is held inside the host-global flock (each with a
mutation-confirmed red-then-green). The "governed callers" claim was true only as
of this round-2 amendment — but it UNDER-COUNTED (see round-3).

## Round-3 correction (the honesty record)

Round-2 governed the OAI harvest + the on-demand/fallback PDF fetch but LEFT THE
EXPORT-SEARCH API UNGOVERNED — so the count was THREE, not the full FOUR.
`client._http_get` issued a **bare `httpx` GET** to `export.arxiv.org/api/query`
— the endpoint the diligence-of-record names as the one that historically
IP-banned the box — reached in production via `client.search` /
`client.fetch_by_id` from both operator CLIs. The CLIs' per-call
`throttle.wait_if_needed()` was the exact bare in-process pattern M1 declared
insufficient: two host jobs (a search + a harvest) could each read the same
`last_request_at` and both fire inside one 3s window. The round-2 lint MISSED it
because the lint keyed on a **static `arxiv.org` URL literal** near the call, and
the search URL is a `_build_search_url(...)` RETURN VALUE (a non-literal) — a real
ungoverned-egress bypass the lint exited 0 on.

Round-3 (a) routes `client._http_get`'s send through `governed_request`, threading
the CLI-owned `ArxivThrottle` down so the 429 sentinel persists across
invocations; (b) added caller-level red-then-green tests that drive the REAL
`client.search` concurrently with an OAI harvest, sharing the canonical state +
lock, asserting the recorded requests are >= the min spacing apart (mutation
confirmed: removing the governor wrapping from `_http_get` makes them fire 0s
apart — RED); and (c) **redesigned the lint** so it can no longer miss this class:
it now flags ANY raw httpx/requests egress in an arXiv-egress module that is not
lexically routed through `governed_request`, **regardless of the URL value** (a
dynamic / DB-derived / return-value URL is caught too). The lint was confirmed to
have teeth on the real bypass — before the `client.py` fix, the redesigned lint
flags `_http_get`'s two raw egresses.

## Round-4 correction — the ROOT (the honesty record)

Rounds 1-3 each fixed ONE more ungoverned egress because the enforcement was
**directory-scoped**: the lint only scanned `acquisition/arxiv/`, so any
arXiv-host fetch OUTSIDE that directory was invisible. The 5th adversarial pass
found the next instance — `acquisition/openaccess/unpaywall.py::download_pdf`
fetching `https://arxiv.org/pdf/<id>` (the OpenAlex `best_oa_pdf_url` for an
arXiv-mirrored work) under the OA throttle: in-process 0.2s spacing (5 req/s), no
flock, no shared state, no ban sentinel — concurrency-blind to the OAI harvest,
and INVISIBLE to a directory-scoped lint. Patching that one symptom would have
been the fourth round of the same mistake.

Round-4 fixes the ROOT so this is the LAST instance, by making governance
**host-based, not location-based**:

1. **`govern_if_arxiv(url, send)`** — a fetch-boundary helper in
   `rate_governor.py` that parses the URL's host at runtime and routes an arXiv
   host (`arxiv.org` / `export.arxiv.org` / `*.arxiv.org`) through the host-global
   governor on the canonical shared throttle state, while calling a non-arXiv
   host's send directly. The host check is at the boundary on the resolved URL, so
   it is bypass-proof regardless of which module fetches.
2. **Every external fetcher in the acquisition tree** routes its send through
   `govern_if_arxiv` (or `governed_request` for a statically-arXiv host) — the OA
   PDF fetchers (`unpaywall`, `pmc`), the OA metadata fetchers (`unpaywall`,
   `pmc`, `doaj`, `openalex`), the arbitrary-URL fetchers (`urls/client`,
   `podcasts/client`), and the API clients (`voice`, `search/exa`,
   `books/public_domain`). The OA fetchers reach the **canonical** `ArxivThrottle`
   (`canonical_arxiv_throttle()`), so an OA-sourced arXiv fetch shares state +
   flock with the harvest / pdf_fetch / search.
3. **The lint is host-based** — it scans all of `acquisition/` and flags any raw
   external fetcher not routed through `govern_if_arxiv` / `governed_request`,
   regardless of URL. Proven (a) it catches a raw egress OUTSIDE
   `acquisition/arxiv/` (a synthetic `acquisition/openaccess/rogue.py`), and (b)
   run against the PRE-FIX shape of `unpaywall.download_pdf` it flags both raw
   egresses — i.e. it WOULD have caught the round-3 bypass.

Caller-level red-then-green (mutation-confirmed): an OA ingest of an arXiv-mirrored
work (`download_pdf` → `arxiv.org/pdf/<id>`, MockTransport) running concurrently
with an OAI harvest, sharing the canonical state + lock, records its arXiv request
>= 3s after the harvest's — and goes RED (0s apart) if the `govern_if_arxiv`
wrapping is removed. `govern_if_arxiv` to a NON-arXiv host does NOT acquire the
flock (asserted: the non-arXiv send completes while a first governor holds the
canonical lock). And the OA channel emits the `arxiv.fetch` audit leg when it
lands an arXiv-host servable body, so `trace(con, arxiv_id)` covers OA-sourced
arXiv fetches too (RED if the leg call is removed).

## Round-5 correction — the TRANSPORT-LAYER terminating fix (the honesty record)

Round-4 made governance host-based but checked the host of the **initial url
only**, while every fetcher uses `follow_redirects=True`. The 5th/6th adversarial
passes found the residual: a NON-arXiv URL that **302-redirects to
`arxiv.org/pdf/<id>`** issued a real, UNGOVERNED GET to arXiv — `govern_if_arxiv`
saw the non-arXiv initial host and called `send()` directly, then httpx followed
the redirect to arXiv with no flock / spacing / ban. This was **LIVE on the OA
path**: `acquisition/openaccess/openalex.py` feeds `oa_url` landing / DOI-resolver
candidates (which redirect to arXiv PDFs) into
`acquisition/openaccess/unpaywall.py::download_pdf`.

The terminating fix governs at the **per-request (per-hop) level**, so the
governor is structurally unable to miss an arXiv request:

1. **An httpx `request` event hook** (`install_arxiv_request_hook`, and the
   `arxiv_governed_client(...)` factory that builds a client carrying it). The
   hook fires for EVERY request the client issues — the initial AND each redirect
   hop — and, when the hop's host is arXiv, applies the host-global governor wait
   (re-entrant flock + ≥3s spacing + `banned_until` check on the canonical
   `~/.antiek/arxiv_throttle.json` + `.governor.lock`) BEFORE that hop goes out. A
   paired `response` hook records the 429 ban sentinel per arXiv hop. A
   non-arXiv→arXiv 302 is therefore governed by construction.
2. **The redirect-prone / variable-URL fetchers build their client via
   `arxiv_governed_client` (or install the hook on a caller-supplied client):**
   `openaccess/unpaywall.download_pdf`, `openaccess/pmc.download_pdf`,
   `urls/client.fetch`, plus the arXiv-direct fetchers `arxiv/pdf_fetch.fetch_pdf`
   and `arxiv/adapter._default_fetch_pdf` (which 302 within arXiv). The hooks share
   the canonical throttle state + flock with the harvest / search.
3. **Reconciliation — governed exactly once.** The outer `governed_request`
   governs + claims the initial hop; the hook skips it and governs only redirect
   hops; the flock is re-entrant so the nested acquisition does not deadlock. Two
   different throttle instances never cross-consume a claim (the claim is matched
   by throttle identity), so the named seams pass the same throttle to both the
   outer governor and the hook.

**`fetch_url` (the LLM-callable builtin, `substrate/graph/rlm_tools.py`).**
`fetch_url(url)` is registered as a builtin tool (`_BUILTIN_TOOLS["fetch_url"]`)
and re-exported from `substrate.graph` — an LLM could call it with an arXiv URL.
It uses `requests`, not httpx, so the event hook does not apply. **It is now
fully fixed, not deferred:** it follows redirects MANUALLY with
`allow_redirects=False` and routes **each hop on its own host** through
`govern_if_arxiv` (re-checking the `Location` host each iteration, capped at 10
redirects), so an arXiv hop — initial OR a redirect target — is held under the
host-global gate and a non-arXiv→arXiv 302 can no longer reach arXiv ungoverned.
The sibling `web_search` builtin (static `serpapi.com` / `html.duckduckgo.com`
hosts) was routed through `govern_if_arxiv` too — a no-op for those non-arXiv
hosts, but it keeps `substrate.graph`'s exported fetchers uniformly on the
governed seam. **No residual `requests`-redirect risk remains** for either tool.

**The lint scope was extended to `substrate/graph/`** (`_EGRESS_SCAN_DIRS =
("acquisition/", "substrate/graph/")`) so a raw external fetcher exported outside
the acquisition tree (the `fetch_url` class) is flagged. The receiver-shape check
keeps the many dict / DuckDB-connection `.get` / `.execute` calls in that tree
from false-flagging. Self-tested: a synthetic `substrate/graph/rogue_tool.py` raw
`requests.get` is flagged; the same fetch routed through `govern_if_arxiv` is
clean.

Caller-level red-then-green (mutation-confirmed in-test): the REAL
`unpaywall.download_pdf` of a NON-arXiv landing URL that 302-redirects to
`arxiv.org/pdf/<id>`, run concurrently with an OAI harvest sharing the canonical
state + lock, records its arXiv (redirect-target) request ≥ 3s after the
harvest's — and goes RED (the arXiv hop never touches the throttle, fires
un-spaced) when the request hook is disabled. A non-arXiv→non-arXiv redirect chain
does NOT acquire the flock (no false governance). The existing direct-arXiv
governance still holds with no double-wait (a single recorded wait, not 2×spacing)
and no deadlock (re-entrant flock).

## What is MECHANICAL vs OPERATIONAL (the honest boundary)

**MECHANICAL (enforced by code on this host):**

- The >= 3s spacing and the 429 `banned_until` sentinel hold **GLOBALLY across
  every arXiv job ON THIS HOST**. Any process that routes its send through
  `governed_request` blocks on the same flock and shares the same JSON state, so
  two host jobs can never both fire in one 3s window, and a ban one job records
  is observed atomically by the next job to take the lock.
- CI red on ANY ungoverned arxiv egress: `rate_governor_check.py` (round-4
  **host-based** redesign) scans the **whole acquisition tree** and flags any raw
  external HTTP fetcher (an egress-verb call on an httpx/requests-client-shaped
  receiver, or a bare `urlopen`) that is not lexically routed through
  `govern_if_arxiv` / `governed_request`, **regardless of the URL value** — so a
  runtime-resolved arXiv URL in ANY module (e.g. the round-3
  `unpaywall.download_pdf` bypass) is caught. The governed seam = the governor
  itself + `throttle.py`, plus any `send` closure handed to `govern_if_arxiv` /
  `governed_request`. There is **no whole-directory allowlist** any more (the
  round-3 `_ARXIV_EGRESS_DIRS = ("acquisition/arxiv/",)` scope, and the
  `acquisition/books/public_domain.py` name-allowlist, are GONE — they were the
  structural cause of the recurring misses); `public_domain.py` is recognized as
  governed by the same structural rule, because it now routes through
  `govern_if_arxiv` like every other fetcher. (`tools/` carries no arXiv egress —
  its only HTTP is a localhost demo client to the Antiek API — so it is out of
  scope; add it to `_EGRESS_SCAN_DIRS` if that ever changes.)

**OPERATIONAL (NOT enforceable from one box — a policy, not a guarantee):**

- **"No multi-IP circumvention" is NOT mechanically enforced.** A flock and a
  JSON file on *this* machine cannot see or stop a **second physical machine /
  IP** running its own scraper — that traffic never touches this lock or this
  state file. arXiv's ban is IP-scoped, so a second IP is also a second ban
  surface, but nothing in this codebase can prevent it. Treating "multi-IP" as
  "enforced" would be a false claim.
- The standing policy is therefore: **do not run a second un-governed scraper,
  and do not run arXiv ingestion from a second IP against the same campaign.**
  All host arXiv egress must go through the governor (CI defends the host case).

## Reverse-if

If arXiv ingestion is ever distributed across multiple hosts/IPs deliberately, a
real cross-host coordinator (a shared rate-limit service, not a local flock) is
required — the local-flock guarantee does not extend across machines, and this
doc must be revisited before any such distribution.
