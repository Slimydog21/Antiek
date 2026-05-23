# Antiek × Exa × Browserbase — Web Retrieval & Live Browsing Integration Spec

**Status**: Draft v1, 2026-05-21. AnchorBrowser-vendor verdicts added 2026-05-23 (§5 matrix rows, §9.1 Wedge 4 candidates, §12.10 REJECT, §14.4.1 Plan B, §15.2 cross-reference) — no code changes; mono-vendor Browserbase escalation unchanged.
**Scope**: Decide where Exa (neural search + cleaned content API) and
Browserbase (hosted headless Chromium + Stagehand) integrate into Antiek's
acquisition path, where each is deferred behind unlock criteria, and which
adoption shapes are explicitly rejected as category errors or substrate
violations. Produce defensible verdicts, not consensus hedging.
**Predecessor docs** (precedence in this order on conflict):
1. `architecture_notes.md` — substrate-level commitments (load-bearing).
   Especially §2.1 (typed event log), §2.3 (DuckDB single-writer), §7
   (schema discipline), §9 (wrestling event vocabulary), §13 (four-layer
   HTML/rendering model).
2. `master-product-spec.md` — product vision + sprint sequence. Especially
   §6 (primary source connection), §7 (continuous research mode), §9
   (IP attribution + retrieval-time gating, Sprint 18 gate), §16
   (no pre-building for hypothetical users).
3. `strategy/voice-and-style-discipline.md` — synthesis quality bar (relevant
   because web-sourced content can be lower-quality and must not contaminate
   synthesis voice).
4. Peer integration specs: `integration_prime_intellect.md`,
   `integration_autoresearch.md`, `integration_posthog.md`,
   `daytona_integration_spec.md`, `rlm_integration_spec.md`.
**Operator quality bar**: intellectual honesty, rigor, defensibility.
Explicit REJECT verdicts where warranted. No "Exa is hot, ship it" or
"Browserbase is necessary because the agent should be able to browse"
framings. The right question is always: *what specific Antiek problem
does this primitive solve, and is it a better solve than what we'd build
or already have native?*

---

## Table of contents

1. [What Exa and Browserbase actually are (and what's reusable)](#1-what-exa-and-browserbase-actually-are-and-whats-reusable)
2. [What they are NOT — the misreadings to avoid](#2-what-they-are-not--the-misreadings-to-avoid)
3. [The single architectural decision that drives every wedge below](#3-the-single-architectural-decision-that-drives-every-wedge-below)
4. [Mapping each primitive to Antiek's substrate](#4-mapping-each-primitive-to-antieks-substrate)
5. [Verdict matrix](#5-verdict-matrix)
6. [Wedge 1 — `acquisition/search/exa` discovery adapter](#6-wedge-1--acquisitionsearchexa-discovery-adapter)
7. [Wedge 2 — Browserbase as escalation fallback inside `acquisition/urls/`](#7-wedge-2--browserbase-as-escalation-fallback-inside-acquisitionurls)
8. [Wedge 3 — Exa `/contents` for in-loop verifier-tier fact lookup](#8-wedge-3--exa-contents-for-in-loop-verifier-tier-fact-lookup)
9. [Wedge 4 — Stagehand-driven extractor for one structured-data surface](#9-wedge-4--stagehand-driven-extractor-for-one-structured-data-surface)
10. [Wedge 5 — Exa Websets for continuous research mode](#10-wedge-5--exa-websets-for-continuous-research-mode)
11. [Wedge 6 — Full agentic browsing as a first-class role](#11-wedge-6--full-agentic-browsing-as-a-first-class-role)
12. [Explicit rejections (don't re-litigate)](#12-explicit-rejections-dont-re-litigate)
13. [Cost, legal, and safety envelope](#13-cost-legal-and-safety-envelope)
14. [Risks and mitigations](#14-risks-and-mitigations)
15. [Unlock criteria for promoting wedges](#15-unlock-criteria-for-promoting-wedges)
16. [Sprint placement](#16-sprint-placement)
17. [Open questions (genuinely unresolved)](#17-open-questions-genuinely-unresolved)
18. [What to do now](#18-what-to-do-now)

---

## 1. What Exa and Browserbase actually are (and what's reusable)

Read carefully. Both products are commonly conflated as "agent web tools";
they solve different layers and the spec breaks down if you treat them as
substitutes.

### 1.1 Exa

A search API plus a cleaned-content-extraction API, both LLM-optimized.
Three endpoints worth caring about:

- **`POST /search`** — neural / keyword / auto search. Returns ranked
  result URLs with title, published date, author, and an optional
  `text` field (truncated body). Supports filters: `includeDomains`,
  `excludeDomains`, `startCrawlDate`, `category` (`research paper`,
  `news`, `linkedin profile`, `company`, `github`, `tweet`, …),
  `numResults` up to 100.
- **`POST /contents`** — given a list of URLs, returns the cleaned
  full-text content as either `text` (markdown-ish) or `highlights`
  (LLM-extracted relevant spans), with optional `summary` (LLM-generated
  per-page summary against an operator-supplied schema) and `livecrawl`
  (force re-crawl if the indexed copy is stale).
- **`POST /findSimilar`** — given one URL, return URLs Exa thinks are
  semantically similar. Useful for "I have one good source, find five
  more like it."

Plus a thin **`/answer`** endpoint that does search + content + LLM
synthesis in one call. We will not integrate this — it collapses the
attribution chain.

Pricing (as of 2026-Q1, verify before any sprint commit): roughly
$5 per 1k searches, $5 per 1k contents pages, $1 per 1k findSimilar
calls. Free tier exists. SDK: official `exa-py` and `exa-js`.

**The Exa-shaped problem class:** I want to find pages that exist
somewhere on the public web that are *semantically* about X (not just
keyword-matching X), with reasonable freshness and de-duplication, and
I want the page body already cleaned to text/markdown so I don't have
to run my own HTML extractor for every page.

### 1.2 Browserbase

A hosted-Chromium-as-a-service. Three layers worth caring about:

- **Raw Playwright connection.** You drive a real Chromium instance
  living on Browserbase's infrastructure via Playwright's standard
  CDP-over-WebSocket. Stealth fingerprinting, proxy rotation, residential
  IPs, captcha-solving (via a separate add-on) are configurable. You
  pay per session-minute. Persistence: optional "contexts" preserve
  cookies/localStorage across sessions.
- **Stagehand SDK.** Browserbase's higher-level abstraction. Three
  methods on top of Playwright:
  - `page.act("click the cookie accept button")` — LLM decides which
    DOM node to interact with, returns success/failure.
  - `page.extract({ schema: <zod schema>, instruction: ... })` — LLM
    extracts structured data from the current DOM against a schema.
  - `page.observe("find the search box")` — LLM returns a list of
    candidate locators without acting.
  All three round-trip through an LLM (configurable; defaults to OpenAI
  but can use Anthropic / OpenRouter).
- **Director.** Browserbase's natural-language browser-agent product.
  Higher-level than Stagehand; we will not integrate (see §11).

Pricing: roughly $0.10 per active session-minute, plus ~$0.0005 per
Stagehand LLM call (small models, fast). Sessions run typically
30s–5min. So one Browserbase page-fetch costs ~50× to 5000× more than
one `httpx.get(...)`. **This number drives every verdict below.**

**The Browserbase-shaped problem class:** I need to interact with a
page — log in, click, scroll-to-load, dismiss a modal, submit a form,
or just render a JS-heavy SPA — to get to content that a plain HTTP
GET can't reach. The premium is justified per-page only when the page
is high-value enough to be worth 50–5000× the marginal cost.

### 1.3 What both products share

Both are **acquisition-layer** services. They are not dispatch
providers (they are not LLMs), they are not roles (they have no opinion
on what to do with the data), they are not graph operators. They sit
*upstream* of `acquisition/urls/adapter.py` in the data flow.

This framing is load-bearing for §3 below.

---

## 2. What they are NOT — the misreadings to avoid

These are the framings that look plausible but are wrong for Antiek's
state. Each becomes a REJECT in §12 unless explicitly upgraded.

### 2.1 Exa is NOT a replacement for `acquisition/urls/`

`acquisition/urls/` is the URL → substrate adapter: it owns the stable
`doc-url-<sha256[:16]>` document id (`acquisition/urls/adapter.py:76`),
the source-tier assignment, the `DocumentLoadedPayload` event emission,
the chunking, the embedding, the graph writes. Exa returns a URL plus a
cleaned text body — that's the input *to* this adapter, not a substitute
for it. If we let Exa's `/contents` output land in the graph directly
without going through `acquisition/urls/adapter.ingest_url(...)`, we
fork two paths for "a URL became a Document," with different doc-id
shapes, different event emission, and different idempotency. The
substrate-as-source-of-truth invariant breaks.

### 2.2 Browserbase is NOT a default fetcher

`acquisition/urls/client.fetch(...)` works for ~80% of the public web
because most pages still serve usable HTML on a plain GET. Browserbase
costs 50–5000× more per page. Promoting it to default would 50–5000×
the per-page acquisition cost for a marginal coverage gain on the long
tail. The defensible posture is escalation, not replacement (Wedge 2).

### 2.3 Exa `/answer` is NOT a synthesis primitive

Exa's `/answer` endpoint does search → content → LLM synthesis in one
opaque call. Antiek's synthesis is a typed-event sequence
(`DecomposeQuestionRequested` → `KeywordsExtracted` → … →
`SynthesisArchived` per `substrate/schemas/events.py`). Substituting
`/answer` for any of that collapses the trajectory — the operator
cannot replay it, the verifier-tier cannot grade it, the event log
cannot reconstruct what was actually retrieved. Hard reject (§12.5).

### 2.4 Stagehand's `page.extract` is NOT a substitute for `parameter_extractor`

`roles/parameter_extractor/` is the role that mints typed nodes and
edges from chunked document text. It runs against the substrate's
chunk table, not against live DOM. Stagehand's `page.extract` runs
against a live DOM in a browser session — different input medium,
different schema lineage. The latter could feed the former (Wedge 4),
but it cannot replace it. The misreading is "Stagehand does extraction
so it does what `parameter_extractor` does." It doesn't.

### 2.5 Neither product bypasses the Sprint 18 retrieval-time legal gate

`master-product-spec.md` §9 commits Sprint 18 to a retrieval-time
gating system for restricted content (Bartz / Hachette / AG MDL legal
corpus restrictions). That gate enforces at the SQL-WHERE level
(`substrate/legal_gate/...`). **Exa search results from a banned
domain hit the gate the same way a manually-typed URL does.**
Browserbase session that lands on banned-domain content hits the same
gate. Integrating either does not authorize bypass; both are
*upstream* of the gate, not around it.

### 2.6 Exa's index is NOT comprehensive

Exa indexes the public web but with their crawler's coverage, freshness,
and recency biases. Specifically:
- Paywalled news (NYT, WSJ, FT) appears in search results but `/contents`
  returns the paywall page, not the article.
- Many SaaS app pages (logged-in dashboards, internal docs) are not
  indexed at all.
- Real-time content (tweets, livestreams) is best-effort and lags.
- Some site operators rate-limit Exa or block their crawler.

Treating Exa as "the public web" is a category error. It's "Exa's
neural index of the public web, with their crawler's blind spots."

### 2.7 Browserbase is NOT a way to avoid building scrapers

The Stagehand pitch is "natural-language browser automation, no
brittle selectors." This is true for one-off extraction but **breaks
down at scale.** Stagehand's LLM calls add latency (3-10s per `act`/
`extract`), cost (~$0.0005 each, accumulates), and non-determinism
(same page, different runs, sometimes different extractions). A
high-volume scraper still wants typed selectors; Stagehand is for
the exact opposite use case — one or two pages where building a
typed scraper is more expensive than tolerating Stagehand's noise.

---

## 3. The single architectural decision that drives every wedge below

**Exa and Browserbase are not the same layer. They must not share an
adapter. They must not share a config namespace. They must not share
an environment variable prefix.**

The clean split:

```
┌──────────────────────────────────────────────────────────────────┐
│  DISCOVERY LAYER (which URLs to ingest)                          │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ acquisition/search/                       NEW MODULE      │   │
│  │   exa/client.py        — typed Exa SDK wrapper            │   │
│  │   exa/adapter.py       — Exa search → DiscoveryProposed   │   │
│  │                          events → URL list                │   │
│  │   exa/README.md                                           │   │
│  │ (future siblings: serpapi/, tavily/, perplexity/)         │   │
│  └───────────────────────────────────────────────────────────┘   │
│                          │                                        │
│                          ▼   one URL per Discovery row            │
│                                                                   │
│  INGESTION LAYER (turn a URL into a Document)                    │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ acquisition/urls/                         EXISTING        │   │
│  │   client.py            — httpx primary fetcher            │   │
│  │   client_browserbase.py — Browserbase escalation fallback │   │
│  │                          (NEW, behind feature flag)       │   │
│  │   adapter.py           — fetch → markdown → graph writes  │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

The contract between the two layers is **a URL**, not a content blob.
Discovery proposes URLs; ingestion turns URLs into substrate. The
`acquisition/urls/adapter.ingest_url(...)` call is the single
substrate-write seam — there is no second path.

This split has three consequences that every wedge below honors:

1. **One doc-id formula.** `url_doc_id(final_url)` in
   `acquisition/urls/adapter.py:76` remains the only way to mint a
   document id for a URL-sourced document. Exa results, Browserbase
   sessions, manual operator pastes — all route through the same id.
   Idempotent across discovery sources.
2. **One event emission point.** `DocumentLoadedPayload` is emitted
   exactly once per document, from `acquisition/urls/adapter.py`.
   Discovery emits its own events (`DiscoveryProposed`,
   `DiscoverySelected`, etc. — defined in Wedge 1) but those are
   discovery-layer events, not document-layer events. The trajectory
   log distinguishes "we considered this URL" from "we ingested this
   URL."
3. **One legal gate.** The Sprint 18 retrieval-time gate sits *between*
   discovery and ingestion. Exa returns a URL; the gate decides
   whether `ingest_url(...)` can run. This is the only viable place to
   put the gate without leaking restricted content into the graph.

If a future wedge proposes violating this split, the wedge is rejected
on architecture grounds before any cost/value analysis. The split is
prior to the wedge selection.

---

## 4. Mapping each primitive to Antiek's substrate

| Primitive | Closest Antiek analog | Mapping cleanliness | Layer |
|---|---|---|---|
| Exa `/search` (neural) | `acquisition/arxiv/client.search`, `acquisition/twitter/adapter` (keyword-driven discovery) | **Strong analog — pure discovery layer addition.** Same shape: query → result URLs → operator picks → ingest | Discovery |
| Exa `/search` (`category="research paper"`) | `acquisition/arxiv/client.search` | Weak — arXiv has its own API, no Exa middleman needed; using Exa for arXiv would add latency and cost with no quality gain | Discovery |
| Exa `/contents` (full text) | `acquisition/urls/extract.html_to_markdown` | **Mixed — pre-extracted text overlaps with Antiek's own extractor.** Cleaner path: Exa returns URL, Antiek fetches + extracts. `/contents` only justified when Exa's index has a copy and the live page is unreachable / paywalled / 404'd since crawl | Ingestion-adjacent |
| Exa `/contents` (`summary` against schema) | `roles/parameter_extractor/` | Anti-mapping — summary collapses to a single LLM call against Exa's choice of model, with no Antiek event trace. `parameter_extractor` is the source of truth for typed extraction. **Reject §12.4** | — |
| Exa `/contents` (`highlights`) | Loop 2's region-selection + claim distillation | Weak — highlights are LLM-judged spans without grounding back to chunk indices; Antiek's claim grounding requires substrate chunk references | — |
| Exa `findSimilar` | "Cross-doc question answered" pattern in `substrate/cross_graph/` | Medium — Exa's similarity is *to* its index; Antiek's similarity is over the operator's own graph. Useful for *discovery expansion* (find more sources like this one) but distinct from substrate similarity | Discovery |
| Exa `/answer` | Loop 1 synthesis | Anti-mapping — collapses the entire trajectory into one opaque call. **Reject §12.5** | — |
| Exa Websets | `compounding/continuous_research.py`, master-product-spec §7 continuous research mode | Medium analog with a real overlap concern — both monitor sources over time. Distinct enough to be complementary (Wedge 5), but the boundaries need explicit definition | Discovery / monitoring |
| Browserbase raw Playwright | None — Antiek has no live-browser primitive | New capability — but only justified per-page when the page is high-value. **Wedge 2 as escalation fallback only** | Ingestion |
| Stagehand `page.act` | None — Antiek does not click | New capability. Only meaningful inside Wedge 4 (one specific structured-data surface). General "agent that clicks" is Wedge 6 — DEFER | Ingestion / interaction |
| Stagehand `page.extract` | `roles/parameter_extractor/` (against chunks), `roles/note_taker/` (against chunks) | Weak — DOM-time extraction is structurally different from chunk-time extraction; preserving the typed event log requires chunk-time extraction stays primary | — |
| Stagehand `page.observe` | None | Internal to Wedge 4 if it ships | — |
| Browserbase Director (NL browser agent) | None — and shouldn't have one this sprint | Anti-mapping — full agentic browsing requires multi-step state, undo, cost discipline, and a UI surface for operator to review. **Wedge 6 DEFER** | — |
| Stagehand "contexts" (persistent cookies) | None | Conditional — only meaningful if a wedge requires logged-in browsing (Wedge 4 might; Wedges 2 and 3 do not) | — |

**The cleanest wins** are Exa search (Wedge 1) and Browserbase
escalation (Wedge 2). The cleanest mid-confidence wins are Exa
`/contents` for verifier-tier corroboration (Wedge 3) and one narrow
Stagehand extractor (Wedge 4). The high-risk shapes are Websets
(monitoring overlap, Wedge 5) and full agentic browsing (Wedge 6 —
DEFER).

---

## 5. Verdict matrix

| Wedge | What it is | Verdict | Sprint |
|---|---|---|---|
| **Wedge 1: `acquisition/search/exa` discovery adapter** | New module: Exa `/search` + `findSimilar` returning a stream of `DiscoveryProposed` events; operator-curated promotion to `ingest_url` | **INTEGRATE NOW** | Sprint 18-19 (sequence with retrieval-time gating; gate must land before Wedge 1 writes graph data) |
| **Wedge 2: Browserbase escalation fallback in `acquisition/urls/client.py`** | When httpx fetch returns `low_word_count` or fails JS-detect heuristic, *optionally* (operator opt-in or flagged on doc) re-fetch via Browserbase. Behind feature flag, off by default | **INTEGRATE NOW** | Sprint 18-19 |
| **Wedge 3: Exa `/contents` as verifier-tier corroboration tool** | The verifier tier (Grok 4.3 via Hermes) gets a tool: `exa_lookup_claim(claim_text, k=3)` → returns 3 URLs with text snippets that support / refute the claim. Used during `RUBRIC_SCORED` and `claim.grounding_check` | **INTEGRATE PHASE 2** | Sprint 19+ (gated on Wedge 1 ratification + verifier-tool-call infrastructure existing) |
| **Wedge 4: Stagehand-driven extractor for one structured-data surface** | One narrow surface where the operator needs login-gated structured data (e.g. SEC EDGAR full-text search results page, or a specific paywalled academic database). Stagehand `page.act` + `page.extract` against a typed Pydantic schema | **INTEGRATE PHASE 2 (conditional)** | Sprint 20+, only if a concrete data need surfaces |
| **Wedge 5: Exa Websets for continuous research mode** | Continuous research (master-product-spec §7) uses Exa Websets as one monitoring source. Webset cron → operator-reviewed discovery queue | **DEFER** | Sprint 21+, gated on continuous research mode having shipped on a non-Exa baseline first |
| **Wedge 6: Full agentic browsing as a first-class role** | A `roles/web_browser/` that takes a goal ("find Tesla's Q3 deliveries by segment from their IR site") and uses Stagehand to navigate freely | **DEFER (possibly REJECT permanently)** | No earlier than Sprint 23+; explicit unlock criteria in §15.6 |
| **Use Exa as a dispatch provider** | Add Exa to `substrate/dispatch/providers/` | **REJECT** | — |
| **Use Browserbase as a dispatch provider** | Add Browserbase to `substrate/dispatch/providers/` | **REJECT** | — |
| **Use Exa `/answer` for synthesis** | Replace or augment `roles/synthesizer/` with Exa's hosted answer endpoint | **REJECT** | — |
| **Use Exa `/contents` summary-against-schema as `parameter_extractor`** | Replace `roles/parameter_extractor/` with Exa's hosted schema summary | **REJECT** | — |
| **Use Browserbase as the default URL fetcher** | Replace `httpx` in `acquisition/urls/client.py` with Browserbase | **REJECT** | — |
| **Use either to bypass the Sprint 18 retrieval-time legal gate** | "Exa results come from Exa, not from us, so the legal gate doesn't apply" | **REJECT** (with extreme prejudice) | — |
| **Use Browserbase to bypass robots.txt or paywalls** | Use stealth-fingerprinting to access content the site operator declined to allow | **REJECT** | — |
| **Bundle a Browserbase session per investigation** | One persistent session per investigation, kept warm | **REJECT (for now)** | — |
| **AnchorBrowser as Wedge 2 Plan B** | Named-alternative escalation fetcher if Browserbase fails §15.2 acceptance or becomes unavailable. Adapter shape (`_SessionLike` + injectable `page_runner` in `client_browserbase.py`) already accommodates a ~150-LOC port to `client_anchorbrowser.py` — don't write the code now; name the contingency | <span class="tag defer">DEFER (named alternative)</span> | Triggered on Browserbase §15.2 failure or unavailability |
| **AnchorBrowser `agent.task` as Wedge 4 candidate** | `agent.task(description, outputSchema=...)` returning structured data — 1:1 analog to Stagehand's `page.act` + `page.extract`. Listed alongside Stagehand; vendor pick happens at §15.4 unlock, not now | <span class="tag defer">DEFER (listed alongside Stagehand)</span> | Conditional on §15.4 surface ratification |
| **AnchorBrowser running in parallel with Browserbase** | Concurrent dual-vendor escalation — Browserbase for some URLs, Anchor for others | <span class="tag reject">REJECT</span> — see §12.10 | — |
| **AnchorBrowser as the default URL fetcher** | Replace httpx with Anchor | <span class="tag reject">REJECT</span> — same as §12.3 | — |
| **AnchorBrowser as a dispatch provider** | Add Anchor to `substrate/dispatch/providers/` | <span class="tag reject">REJECT</span> — same as §12.2 (not an LLM) | — |
| **AnchorBrowser for paywall / robots bypass** | Use Anchor's stealth/anti-bot tooling to access disallowed content | <span class="tag reject">REJECT</span> — same as §12.7 (policy posture is the gate, not the tooling) | — |
| **AnchorBrowser's MCP server as Antiek's browsing transport** | Use Anchor's MCP surface instead of its SDK | <span class="tag defer">DEFER — no decision needed</span> | Re-evaluate only if Antiek-as-MCP-host (master-spec MCP-first commitment) ratifies first |
| **AnchorBrowser's Web Action Cache for deterministic re-runs** | Record an agent.task and replay deterministically. The strongest Anchor differentiator IF the docs page (404'd 2026-05-23) stabilizes + cache is exportable for `tools/golden_traces/` | <span class="tag defer">DEFER — docs unverifiable</span> | Re-evaluate when public docs + ≥1 operator-runnable demo exist |

---

## 6. Wedge 1 — `acquisition/search/exa` discovery adapter

The first INTEGRATE NOW item. Detailed because it sets the discovery-layer
contract every future search-source wedge will inherit.

### 6.1 What it does

Adds `acquisition/search/exa/` with the following shape:

```
acquisition/search/
  __init__.py
  README.md                  # what the discovery layer is, when to use it
  events.py                  # DiscoveryProposed, DiscoverySelected types
  exa/
    __init__.py
    client.py                # typed Exa HTTP client (httpx, no SDK)
    adapter.py               # search(query, ...) → list[DiscoveryProposed]
    README.md                # Exa-specific knobs, cost notes, blind spots
```

**Operator API** (the seam other code calls):

```python
from acquisition.search.exa import discover

candidates = discover(
    query="Anthropic Claude pricing late 2025 vs 2026",
    investigation_id="inv-...",
    num_results=10,
    include_domains=None,             # optional whitelist
    exclude_domains=("reddit.com",),  # optional blacklist
    category=None,                    # one of Exa's categories or None
    start_published_date="2025-09-01",
)
# candidates: list[DiscoveryProposed], persisted as events, returned for
# operator review. NO graph writes until ingest_url is called.

for c in candidates:
    if operator_accepts(c):
        ingest_url(
            c.url,
            investigation_id="inv-...",
            source_tier=c.suggested_tier,   # adapter's guess; operator can override
        )
```

### 6.2 The data flow, step by step

1. Operator (or a role) calls `discover(query=..., investigation_id=...)`.
2. Exa client makes one `/search` HTTP call against Exa's API.
3. For each result, the adapter:
   - Mints a stable `discovery_id = "disc-exa-" + sha256(url + investigation_id)[:16]`.
   - Computes a `suggested_tier` heuristic (research domain → 2, news →
     3, blog → 4, social → 4).
   - Emits a typed `DiscoveryProposedPayload` event (new payload type,
     defined below). The event carries `discovery_id`, `query`,
     `provider="exa"`, `url`, `title`, `published_date`, `author`,
     `score`, `text_snippet_preview` (≤300 chars).
4. The adapter returns a list of typed `DiscoveryProposed` objects (the
   Python representation of the event), NOT a graph write.
5. Operator-or-caller decides which to promote. Promotion = call
   `ingest_url(...)`. The `DiscoverySelected` event ties the
   `discovery_id` to the resulting `document_id` so the trajectory shows
   "this document came from this Exa query."

### 6.3 New event types

Add to `substrate/schemas/events.py`:

```python
class DiscoveryProposedPayload(_PayloadBase):
    """A discovery-layer source proposed a URL. The URL has NOT been
    ingested; this event is the audit trail of 'what we considered.'
    Promotion to ingestion is a separate event (DiscoverySelected)."""
    discovery_id: str
    provider: Literal["exa", "serpapi", "tavily", "operator", ...]
    query: str
    url: str
    title: Optional[str] = None
    published_date: Optional[str] = None  # ISO-8601 if known
    author: Optional[str] = None
    relevance_score: Optional[float] = None
    suggested_tier: int                   # 1-4 per source-tier system
    text_snippet_preview: Optional[str] = None  # truncated to 300 chars
    provider_response_id: Optional[str] = None  # Exa's request id for audit
```

```python
class DiscoverySelectedPayload(_PayloadBase):
    """A previously-proposed discovery was promoted to ingestion. Ties
    the discovery_id to the resulting document_id when ingestion
    succeeded. document_id is None if ingestion was rejected by the
    legal gate or failed."""
    discovery_id: str
    document_id: Optional[str]
    decision: Literal["ingested", "rejected_by_legal_gate", "rejected_by_operator", "fetch_failed"]
    rejection_reason: Optional[str] = None
```

Update `ActionType` enum:

```python
DISCOVERY_PROPOSED = "discovery.proposed"
DISCOVERY_SELECTED = "discovery.selected"
```

Update the TS codegen at `tools/codegen/emit_types.py` so frontend
discovery review surfaces (Sprint 19+) can render these.

### 6.4 Authentication and configuration

- Environment variable: **`EXA_API_KEY`**. Never share a prefix with
  any other service's key. Never read from `OPENAI_API_KEY`. Never
  fall back to a different key on failure (silent misrouting is worse
  than a loud failure).
- Configuration lives in `acquisition/search/exa/client.py`, not in
  `substrate/dispatch/config.yaml`. Discovery layer is separate from
  dispatch layer.
- Default base URL: `https://api.exa.ai`. Override via constructor for
  tests (`httpx.MockTransport`).
- Default timeout: 30s (longer than the URL fetcher because Exa's
  upstream crawl-on-demand can be slow).
- Retry policy: 429 and 5xx retried with exponential backoff up to 3
  attempts. 4xx other than 429 raises immediately (configuration
  error).

### 6.5 Idempotency and de-duplication

- Same `(query, investigation_id)` pair within 24h: deduplicate by
  short-circuiting to a cached `DiscoveryProposed` list. The
  reasoning: operator running `discover(...)` twice in a session
  should not pay twice for the same Exa call. Cache key is hashed;
  results stored in a new `discovery_cache` DuckDB table.
- Same URL appearing in multiple discoveries (e.g. across different
  queries): each gets its own `DiscoveryProposed` event (different
  `discovery_id`) but `ingest_url(...)` deduplicates downstream via
  `url_doc_id` — there is no double-ingestion.

### 6.6 Source-tier suggestion heuristic

The adapter's `suggested_tier` is a *suggestion*, not an authority.
The heuristic (in `acquisition/search/exa/adapter.py`):

```python
def suggest_tier(url: str, category: Optional[str]) -> int:
    """
    Tier 1: primary source (operator-curated only — NEVER auto-assigned)
    Tier 2: known-good research (arXiv, *.gov, *.edu, doi.org, primary IR pages)
    Tier 3: known-good news (NYT, WSJ, FT, Bloomberg, Reuters, Economist, etc.)
    Tier 4: general web (default)
    """
    if category == "research paper":
        return 2
    host = urlparse(url).netloc.lower()
    if any(host.endswith(s) for s in (".gov", ".edu", "doi.org", "arxiv.org")):
        return 2
    if host in _CURATED_NEWS_TIER_3:    # explicit allowlist
        return 3
    return 4
```

`_CURATED_NEWS_TIER_3` lives in `substrate/constants.py` next to the
existing source-tier definitions. Operator edits it directly. **No
automatic learning of "what's a good source"** — that's a substrate
decision, not a search-API decision.

### 6.7 Cost discipline

- Per-call cost is logged into the event payload (`DiscoveryProposedPayload`
  via a sibling `DiscoveryCostPayload` — or inline as a `cost_usd_estimate`
  field; decide before merge).
- A daily cap of $5 of Exa search spend (configurable via
  `EXA_DAILY_BUDGET_USD`) hard-stops new search calls until UTC midnight.
  When the cap is hit, `discover(...)` raises a typed
  `DiscoveryBudgetExceeded` error that the caller must handle. **No
  silent fallback to a different provider.**
- Roll-up cost reporting: nightly job (extends `runtime/weekly_report.py`)
  emits a discovery-cost summary alongside the existing dispatch cost
  summary.

### 6.8 What this wedge does NOT do

- Does NOT fetch the URLs. `acquisition/urls/adapter.ingest_url(...)` does.
- Does NOT call `/contents`. Wedge 3 introduces `/contents`, gated on a
  separate use case (verifier-tier corroboration).
- Does NOT auto-ingest. Every promotion is an explicit
  `DiscoverySelected` event.
- Does NOT bypass the Sprint 18 legal gate. Discovery proposes URLs;
  the gate decides whether ingestion proceeds. If a discovered URL is
  on the banned-corpus list, ingestion is refused and
  `DiscoverySelected{decision="rejected_by_legal_gate"}` is emitted —
  the discovery is still in the trail (audit) but no graph write
  happens.

### 6.9 Sequencing constraint

**Wedge 1 cannot ship before the Sprint 18 retrieval-time legal gate
is in production.** The reason: Exa returns URLs across the full public
web, including domains the legal gate must restrict. Shipping the
adapter without the gate ingests restricted content. Sequencing is:

1. Sprint 18 — retrieval-time legal gate ships (per
   `master-product-spec.md` §9).
2. Sprint 18 (late) or Sprint 19 (early) — Wedge 1 ships, with
   pre-ingestion gate enforcement and `DiscoverySelected{decision="rejected_by_legal_gate"}`
   wired through.

Skipping the sequencing is a substrate violation. The wedge is
defensible only with the gate first.

### 6.10 Acceptance criteria

- `discover(query=..., investigation_id=...)` returns ≥1 result for a
  well-formed query against the production Exa key.
- Each result emits exactly one `DiscoveryProposedPayload` event,
  visible in the event log JSONL.
- Promoting a result via `ingest_url(...)` emits exactly one
  `DiscoverySelectedPayload` with `decision="ingested"` and a non-null
  `document_id` matching `url_doc_id(final_url)`.
- Promoting a banned-corpus URL emits
  `DiscoverySelectedPayload{decision="rejected_by_legal_gate"}` and
  produces zero graph writes.
- Daily budget cap (`EXA_DAILY_BUDGET_USD`) triggers
  `DiscoveryBudgetExceeded` on the next call after threshold.
- Integration test: one synthetic Exa response (via
  `httpx.MockTransport`) flows through `discover → ingest_url → graph
  writes`, with all events emitted in order, and idempotent re-run
  produces no duplicate graph rows.
- Cost-per-call recorded; weekly_report.py picks up the new line item.

### 6.11 Estimated effort

~4 days of focused work:
- New module scaffold + httpx client + retry/backoff: ~1 day
- Event payload types + Pydantic + TS codegen update: ~half a day
- Idempotency + cache table + daily budget: ~1 day
- Legal-gate integration (assumes gate exists from Sprint 18): ~half a day
- Tests (unit + integration with mock transport + legal-gate paths): ~1 day

---

## 7. Wedge 2 — Browserbase as escalation fallback inside `acquisition/urls/`

The second INTEGRATE NOW item. Narrowly scoped — the failure mode it
addresses is real, but the cost differential demands escalation, not
default-on.

### 7.1 The failure mode this targets

`acquisition/urls/adapter.py:155` already short-circuits when extracted
content is `< MIN_INGEST_WORD_COUNT` (50 words), emitting the
`DocumentLoadedPayload` event but skipping graph writes with
`skipped_reason="low_word_count"`. This is the right behavior for the
common case (paywall, JS-rendered SPA, captcha wall) — pollutes the
graph less and tells the operator what failed.

But sometimes the operator KNOWS the page has content the httpx fetch
can't see (Twitter threads, news sites with aggressive bot detection,
SPAs like LinkedIn job posts, Substack subscriber-only previews that
expose enough text to be useful behind the modal). For those cases,
the current behavior is "give up." Wedge 2 adds one escalation path:
re-fetch with Browserbase.

### 7.2 What it does

Add `acquisition/urls/client_browserbase.py`:

```python
def fetch_via_browserbase(
    url: str,
    *,
    wait_for: Optional[str] = None,         # CSS selector or "networkidle"
    wait_timeout_s: float = 15.0,
    session_pool: Optional[BrowserbaseSessionPool] = None,
    user_agent: Optional[str] = None,
) -> FetchedHtml:
    """
    Drives a Browserbase Chromium session via Playwright.
    Returns the same FetchedHtml shape as client.fetch — drop-in
    compatible with html_to_markdown.

    DOES NOT change the URL adapter contract. DOES NOT emit events
    directly; the adapter's existing event emission still happens.
    """
```

Extend `acquisition/urls/adapter.ingest_url`:

```python
def ingest_url(
    url: str,
    *,
    investigation_id: str,
    source_tier: int = DEFAULT_URL_SOURCE_TIER,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
    http_client: Optional[object] = None,
    fetched: Optional[FetchedHtml] = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
    fallback_to_browserbase: bool = False,         # NEW
    browserbase_wait_for: Optional[str] = None,    # NEW
) -> IngestUrlResult:
    ...
```

The behavior change is **purely additive**:

1. If `fetched` was passed, use it as before. No fallback.
2. Else `fetched = fetch(url)` via httpx, as before.
3. Extract markdown, as before.
4. If `md_doc.word_count < min_word_count` AND `fallback_to_browserbase`
   is True AND the URL is not on a no-fallback list:
   - Re-fetch via `fetch_via_browserbase(url, wait_for=browserbase_wait_for)`.
   - Re-extract.
   - Emit a typed `FetchFallbackEscalatedPayload` event so the
     trajectory shows the escalation happened.
   - Continue with the new content if word_count now passes; else
     skip with `skipped_reason="low_word_count_after_fallback"`.
5. The rest of the flow (event emission, graph writes) is unchanged.

### 7.3 The new event type

```python
class FetchFallbackEscalatedPayload(_PayloadBase):
    """Recorded when the URL adapter escalated from httpx to a heavier
    fetcher (currently Browserbase). Captures cost and the heuristic
    that triggered the escalation."""
    url: str
    primary_fetcher: Literal["httpx"]
    primary_word_count: int
    fallback_fetcher: Literal["browserbase"]
    fallback_word_count: int
    escalation_reason: Literal["low_word_count", "operator_override", "JS-detect"]
    estimated_cost_usd: float
```

Add `ActionType.FETCH_FALLBACK_ESCALATED = "fetch.fallback.escalated"`.

### 7.4 Why escalation, not default

- httpx fetch cost: ~$0.0001 per page (bandwidth + my own electricity).
- Browserbase cost: ~$0.10–$0.50 per session.
- 1000× to 5000× ratio. At Antiek's projected ingestion volume
  (`compounding/continuous_research.py` is designed for 100+ pages per
  day in continuous mode), going default-on means $100–500/day vs
  $0.10/day. That is *not* a defensible delta for a marginal coverage
  gain.
- Default behavior remains: httpx fetches; if it fails, the operator
  sees `skipped_reason="low_word_count"` in the event log, and can
  re-call `ingest_url(url, ..., fallback_to_browserbase=True)`
  manually.

### 7.5 What this wedge does NOT do

- Does NOT log in to anything. Browserbase persistent contexts
  (cookies) are NOT used in Wedge 2. Logged-in browsing is Wedge 4's
  scope and depends on the specific data surface.
- Does NOT execute JavaScript-driven interactions (clicks, scrolls).
  Wedge 2 is a smarter fetcher, not an interaction agent. If a page
  needs `click("Load more")` to expose content, Wedge 2 returns the
  pre-click HTML and the operator decides if it's worth Wedge 4.
- Does NOT bypass robots.txt. The Browserbase fetcher respects
  `robots.txt` (via a polite-pre-check; see `client_browserbase.py`).
  If a site disallows crawling, the fallback does not proceed.
- Does NOT silently retry on captcha. If the Browserbase session
  hits a captcha, the fetch returns the captcha page; the adapter
  treats it as another `low_word_count` skip and emits the event
  with `escalation_reason` truthful about what happened.

### 7.6 Concurrency and session pooling

- Default: one Browserbase session per `fetch_via_browserbase` call,
  torn down at the end.
- Optional: pass a `BrowserbaseSessionPool` (defined in
  `client_browserbase.py`) for batch ingestion to reuse sessions
  across calls — at the cost of carrying state. The pool is opt-in
  per call; the default is no pool.
- Hard cap: max 3 concurrent Browserbase sessions per process. This is
  enforced by a semaphore in the client. The cap exists because
  Browserbase's free / dev tiers cap concurrency, and silent queueing
  past the cap masks failure.

### 7.7 Configuration

- Environment variables: **`BROWSERBASE_API_KEY`**, **`BROWSERBASE_PROJECT_ID`**.
  Never alias to other services' env vars.
- Default per-session timeout: 60s.
- Default total per-day Browserbase budget: $5 (configurable via
  `BROWSERBASE_DAILY_BUDGET_USD`). Hard-stops, no silent fallback.

### 7.8 Acceptance criteria

- `ingest_url(url, ..., fallback_to_browserbase=True)` on a known
  JS-rendered SPA (test fixture: a captured Twitter thread URL that
  httpx returns empty for) produces a non-skipped result.
- Default behavior unchanged: `ingest_url(url, ...)` without the new
  flag uses httpx only and behaves identically to before Wedge 2.
- `FetchFallbackEscalatedPayload` event emitted exactly when fallback
  fired.
- Concurrency cap enforced (4th simultaneous call blocks until one
  finishes).
- Daily budget cap triggers `BrowserbaseBudgetExceeded` typed error.
- Integration test with mocked Browserbase SDK round-trips a fixture
  page.

### 7.9 Estimated effort

~3 days:
- `client_browserbase.py` (Playwright over Browserbase, session pool,
  retry, budget): ~1.5 days
- Adapter wiring + new payload type + event emission + TS codegen: ~half a day
- Tests (unit + integration mocked + concurrency cap + budget cap): ~1 day

### 7.10 Sequencing with Wedge 1

Wedges 1 and 2 are **independent on the substrate** — Wedge 1 doesn't
require Wedge 2 to ship, and vice versa. Sequence either way. Recommended:
Wedge 1 first because the discovery layer is the bigger missing
primitive and Wedge 2 is a fallback on an already-working path.

---

## 8. Wedge 3 — Exa `/contents` for in-loop verifier-tier fact lookup

PHASE 2 — depends on Wedge 1 ratification and the verifier-tier tool-call
infrastructure being defined.

### 8.1 What it does

The verifier tier (Grok 4.3 via Hermes, per
`project_antiek_hermes_bridge.md` memory) currently scores rubrics
against the substrate's own claims. It does NOT independently
corroborate against the public web. Wedge 3 adds one tool:

```python
def exa_lookup_claim(
    claim_text: str,
    *,
    k: int = 3,
    investigation_id: str,
    require_published_after: Optional[str] = None,
) -> list[ExaLookupResult]:
    """
    Searches Exa for ≤k pages whose text appears to support or refute
    the claim. Returns URL + cleaned snippet (NOT full text). Emits a
    typed VerifierLookupPayload event.

    DOES NOT ingest anything into the graph. This is a tool call, not
    an acquisition.
    """
```

The verifier tier calls it during `RUBRIC_SCORED` evaluation or during
`claim.grounding_check`. The returned snippets enter the verifier's
context as **evidence-of-claim-existence-in-the-world**, not as
substrate evidence — the substrate's grounding remains anchored to
ingested documents.

### 8.2 New event type

```python
class VerifierLookupPayload(_PayloadBase):
    """The verifier tier consulted an external corroboration tool.
    Recorded so the trajectory shows when the verifier reached
    outside the substrate."""
    tool: Literal["exa.search_contents"]
    query: str
    claim_text: Optional[str] = None
    k_requested: int
    results: list[ExaLookupResult]
    cost_usd_estimate: float
```

### 8.3 Why the snippets stay out of the graph

The substrate-as-source-of-truth invariant requires that every claim
in the graph traces back to a chunk in an ingested document. Exa
snippets are NOT ingested documents — they have no chunk index, no
section path, no stable position. If a verifier-tier snippet later
becomes substrate evidence, the operator promotes the underlying URL
via `ingest_url(...)` and the claim is re-grounded against the now-
ingested chunk. The verifier-lookup event records what the verifier
considered; the graph records what the substrate believes.

### 8.4 Why this is PHASE 2

Two preconditions:

1. **Wedge 1 must ship first.** The Exa client + budget + event
   plumbing are reused; building them twice is waste.
2. **Verifier-tier tool-call infrastructure does not yet exist in a
   ratified form.** The verifier tier currently scores rubrics in a
   single-shot dispatch. Adding tools introduces multi-turn dispatch
   semantics that touch `substrate/dispatch/`. That's a substrate
   change that should be its own decision, not a side effect of an
   Exa integration. Sprint 19+ depending on dispatch-multi-turn
   readiness.

### 8.5 Goodhart risk

If the verifier always defers to "but Exa returned a corroborating
snippet," it stops doing its actual job (rubric scoring against
Antiek's claim) and reduces to "did Exa find an agreeing page?"
Mitigation:
- The verifier's rubric weighting MUST keep substrate-grounding as
  primary. Exa lookup is a *signal*, not the score.
- Calibration: a curated eval set (per Prime Intellect spec §D)
  with claims where the Exa result is misleading (correct claim,
  no corroborating page; incorrect claim, plenty of agreeing pages
  because the falsehood is popular). The verifier's accuracy with
  Wedge 3 enabled vs disabled must be measured on this set before
  Wedge 3 ships to production scoring.

### 8.6 Unlock criteria

See §15.3.

---

## 9. Wedge 4 — Stagehand-driven extractor for one structured-data surface

PHASE 2 — conditional on a concrete data need surfacing.

### 9.1 What it does

For ONE specific surface where:
- The operator needs structured data (typed fields, not free text).
- The data lives behind login OR aggressive JS rendering OR multi-step
  navigation.
- The volume is low enough that Stagehand's per-page cost is
  acceptable.
- A keyed scraper (typed Playwright selectors) would be too brittle to
  maintain.

…build a Stagehand- *or* Anchor-driven extractor as a single typed
adapter under `acquisition/<source_name>/adapter.py`. Concrete candidates
the operator mentioned in prior sessions:

- **SEC EDGAR full-text search** (logged-out but JS-heavy and slow to
  scrape conventionally) — though EDGAR also has a direct API; if so,
  use it instead and Wedge 4 doesn't apply here.
- **Polymarket markets** (some JS-loaded data) — but Polymarket has an
  API too. Prefer API.
- **One specific academic database paywalled per-institution** —
  conditional on the operator's research workflow demanding it.

**Vendor candidates for the typed extraction primitive (added
2026-05-23):**

- **Stagehand** (`page.act` + `page.extract` against a typed Pydantic
  schema) — the original Wedge 4 candidate. Two-method split is
  inspectable; act/extract steps land in the trajectory individually.
- **AnchorBrowser `agent.task(description, outputSchema=...)`** —
  newer alternative; returns structured data matching a Pydantic schema
  via an internal agent loop ({browser-use, openai-cua, gemini-
  computer-use}). Structurally more opaque than Stagehand (`maxSteps=40`
  black box), which cuts slightly against the trajectory-as-product
  invariant (master-spec §15.4; spec §12.5). Either vendor satisfies
  Open Question §17.7 (vendor's own LLM config, not Antiek's dispatch
  router).

Vendor pick happens at §15.4 unlock — when a concrete surface ratifies.
Not now. Per §12.10, running both vendors concurrently is REJECT.

The wedge is *conditional* because Antiek does not currently have a
ratified specific surface. Until one is named, the wedge is "designed,
not built."

### 9.2 The pattern when it lands

Each Wedge-4 adapter:

1. Lives at `acquisition/<source>/adapter.py` (e.g.
   `acquisition/edgar/adapter.py`).
2. Uses Stagehand for navigation + `page.extract` for typed extraction
   against a Pydantic schema defined in the adapter.
3. Calls `acquisition/urls/adapter.ingest_url(...)` for any URL it
   discovers along the way — so the standard URL-to-document path
   handles those, not Stagehand's `page.extract`.
4. Mints typed nodes/edges directly for the structured data only when
   the data has no underlying URL representation (rare; most things
   on a page can be reached via a URL).
5. Emits `DocumentLoadedPayload` with `media_type="stagehand_extracted"`
   when the structured-data payload IS the document.

### 9.3 Why this is PHASE 2 and conditional

- No specific data surface ratified yet (open question §17.4).
- Stagehand's stability under workload is not directly observed by
  Antiek. Operator should run a 100-page scrape against the candidate
  surface as a spike before committing to a Wedge-4 adapter.
- Per-page cost (~$0.001–$0.005 with Stagehand LLM calls) accumulates
  fast. Volume estimate must precede commit.

### 9.4 Open question — Pydantic schema vs. zod

Stagehand's TS SDK uses zod; the Python SDK uses Pydantic. Antiek's
substrate-side schemas are Pydantic (per `substrate/schemas/events.py`).
Use the Python SDK. The TS surface for any Wedge-4 data lives
downstream of substrate writes, not at extraction time.

### 9.5 Acceptance criteria when it ships

Adapter-specific. Defined per concrete Wedge-4 candidate when the
surface is named.

---

## 10. Wedge 5 — Exa Websets for continuous research mode

DEFER — gated on continuous research mode shipping on a non-Exa baseline
first.

### 10.1 What Websets actually are

Exa's Websets product: define a Webset (a saved search with criteria),
Exa runs it as a continuous job, and you receive new matches as they
appear. Conceptually similar to RSS-for-the-public-web. Per-Webset
pricing applies.

### 10.2 The overlap with `compounding/continuous_research.py`

`master-product-spec.md` §7 describes continuous research mode: the
operator's open questions are watched, sources are revisited, new
documents trigger re-synthesis. The intended implementation is
substrate-native (cron + the operator's existing RSS feeds + arxiv
polling + selected acquisition adapters).

Wedge 5 would add Exa Websets as one monitoring source: instead of
the operator manually choosing which RSS feeds to watch, Exa's
neural-search monitoring runs in their cloud and pushes results.

### 10.3 Why DEFER

- **Substrate-native first.** Continuous research mode must work
  without Exa before Exa is added as a complication. If continuous
  research only works with Exa, the substrate is incomplete.
- **Cost surface is unbounded.** Webset cost scales with
  match frequency, which is not pre-known. Adding Websets before the
  daily-budget pattern from Wedge 1 has been operated on for ≥30 days
  risks runaway cost.
- **Operator hasn't validated the use case.** The continuous research
  cron is designed for low-frequency revisit (daily, not minute-by-
  minute). Webset's value compounds at high-frequency monitoring.

### 10.4 What CAN happen during defer

The discovery layer from Wedge 1 is reusable — when Webset matches
arrive, they flow through `acquisition/search/exa/` as
`DiscoveryProposed` events with `query=<webset_id>` and a different
provider sub-tag. No second adapter, no second event type. The
substrate stays clean.

### 10.5 Unlock criteria

See §15.5.

---

## 11. Wedge 6 — Full agentic browsing as a first-class role

DEFER, possibly REJECT permanently. This is the headline thing the question
"can my agent browse the web" implies, and it's the wrong thing to build
this year.

### 11.1 What it would be

A `roles/web_browser/` role that takes a high-level goal ("find Tesla's
Q3 deliveries by segment from their IR site") and uses Stagehand (or
Browserbase Director) to navigate freely: search, click links, scroll,
follow redirects, extract data, return a result. Multi-step. Stateful.
LLM-in-the-loop on every interaction decision.

### 11.2 Why DEFER

- **Cost is unbounded per goal.** A multi-step browsing session can
  rack up 10-100 Stagehand calls. At ~$0.005 each plus session-minutes,
  one goal = $0.50–$5. Antiek's substrate runs hundreds of goals per
  investigation; this is not bounded.
- **State is hard.** Multi-step browsing requires session resumption,
  rollback on dead ends, deduplication of visited pages, cost ceilings
  per goal — all of which are substrate-level concerns, not
  Browserbase-level concerns. Building this *correctly* is multi-sprint
  work, not "add Stagehand."
- **The substrate already handles the structured cases.** Tesla's
  Q3 deliveries? `acquisition/urls/` pointed at the IR press release.
  Anthropic's pricing? `acquisition/urls/` on the pricing page. The
  cases where free-form browsing wins are the long tail of "I don't
  know the URL." The discovery layer (Wedge 1) addresses that long
  tail better — Exa's neural search finds the URL; the URL adapter
  ingests it.
- **The operator's review surface doesn't exist yet.** An agent that
  freely browses must be observable. The trajectory replay viewer
  (PostHog Wedge 5 — Sprint 20) is the right surface; until it
  exists, browsing trajectories are opaque JSONL.

### 11.3 Why possibly REJECT permanently

If Wedges 1, 2, 3, and 4 together cover ≥95% of the realistic web-
acquisition needs Antiek encounters, Wedge 6 has no remaining demand.
The hypothesis is that the discovery + escalation + corroboration +
narrow-extractor pattern outperforms free-form browsing for Antiek's
research domain, because Antiek is *evidence-anchored* — claims must
be substrate-grounded, not just "the agent saw it on a page." Free-form
browsing is the wrong primitive when the deliverable is grounded
synthesis.

### 11.4 Unlock criteria

See §15.6. They are stringent on purpose.

---

## 12. Explicit rejections (don't re-litigate)

Stated once. The verdicts are settled. Re-open only if the underlying
substrate state changes meaningfully.

### 12.1 REJECT: Exa as a dispatch provider

`substrate/dispatch/providers/` is the LLM provider abstraction —
OpenAI-shaped chat-completions adapters that handle prompt + response
+ usage tracking. Exa is not an LLM. Forcing Exa into the dispatch
abstraction (treating its `/search` as a dispatch call) overloads
the abstraction with two unrelated shapes. Discovery and dispatch are
different concerns. Same rejection logic as Prime Intellect spec §C
(Prime hosted models would be a dispatch provider; Prime as a *runner*
isn't). Exa stays in `acquisition/search/`.

### 12.2 REJECT: Browserbase as a dispatch provider

Same logic. Browserbase is a browser, not an LLM. The Stagehand LLM
calls *inside* a Browserbase session DO use an LLM, but configured
internally — they are not dispatched by Antiek's router and should not
be. The cost-tracking is per-session, not per-token; the abstraction
mismatch is total.

### 12.3 REJECT: Browserbase as the default URL fetcher

50–5000× cost ratio (§7.4). Cannot be defended at Antiek's projected
ingestion volume. The escalation pattern in Wedge 2 captures the value
without the cost. Default-on Browserbase would also tie the URL
adapter's reliability to a third-party SaaS — every continuous research
job would fail when Browserbase has an incident. The httpx primary
keeps the adapter substrate-internal-only at default.

### 12.4 REJECT: Exa `/contents` `summary`-against-schema as `parameter_extractor`

`/contents` with a summary parameter runs an LLM (Exa's choice, with
Exa's prompt, against Exa's chosen model) to extract structured data
from a page. `roles/parameter_extractor/` does the same thing — for
Antiek's chunks, with Antiek's prompts, with Antiek's dispatch tier,
with Antiek's typed event trail. The two systems doing the same job
with different lineages is the misalignment. The parameter_extractor
is the typed-extraction source of truth; Exa's summary is opaque.

If the operator wants Exa's summary, they get it from `/contents`
without Antiek's involvement — but it does not enter the substrate as
parameter-extraction output. The same content goes through
`parameter_extractor` if the document is ingested.

### 12.5 REJECT: Exa `/answer` for synthesis

`/answer` collapses search → contents → LLM into one opaque call.
Antiek's synthesis is a typed-event sequence (Decompose, Keywords,
ParameterExtract, Connect, Synthesize, ConstraintCheck, RubricScore).
Substituting `/answer` for any of those collapses the trajectory.
This is the same rejection shape as Prime Intellect spec §C: external
hosted "do the whole thing" surfaces conflict with Antiek's
trajectory-as-product invariant.

The trajectory IS the product (master-product-spec §15.4). Operations
that collapse it are rejected by category, not by cost.

### 12.6 REJECT: Using either to bypass the Sprint 18 retrieval-time legal gate

The legal gate is at the SQL-WHERE level in
`substrate/legal_gate/` (Sprint 18 deliverable). Any code path that
reaches the graph must pass the gate. **There is no architectural way
to "use Exa to get content from a banned domain" because the gate
sits between the URL and the graph, not between Exa and the URL.**

Stated explicitly because the question will be asked: "Exa already
ingested it, so we're not crawling, we're just reading from Exa's
cache — does the gate apply?" Yes. The gate applies to graph writes,
not to crawls. Reading from Exa's cache and writing to the graph is
a graph write. Gate applies. Period.

### 12.7 REJECT: Browserbase to bypass robots.txt or paywalls

Browserbase offers stealth fingerprinting and residential IPs. These
make a session look more like a real user. Using them to access
content the site operator declined to allow (via robots.txt, IP
blocks, paywall) is not a legal-defensibility position Antiek will
take. The substrate's value depends on the operator's ability to
attribute sources publicly; sources reached by circumventing access
control are not publicly defensible.

This rejection is broader than the AG MDL / Hachette / Bartz legal
gate — that gate concerns specific banned corpora; this rejection
concerns the general norm.

### 12.8 REJECT: Bundling a persistent Browserbase session per investigation

PostHog-style "one persistent session per investigation, kept warm"
sounds efficient but creates two failure modes:
- **State leakage.** Cookies, localStorage, fingerprints accumulate
  across pages. A session that logged in to site A and then visits
  site B leaks site-A identity to site B. Antiek does not control
  what each ad-tech tracker does with this.
- **Cost surface unbounded.** A session kept warm runs the meter
  whether or not it's doing useful work. The escalation pattern in
  Wedge 2 (start a session for one URL, tear it down) bounds cost
  per fetch.

If a future use case requires logged-in browsing (Wedge 4), the
specific adapter manages its own session lifecycle — there is no
investigation-level session.

### 12.9 REJECT: Using Stagehand's `page.act` against substrate UI

A misreading I'd preempt: "Stagehand can navigate Antiek's own web
app." It can. It shouldn't. Antiek's UI is the operator's surface;
having an agent click around the operator's notebook is the inverse of
the workflow. The agent operates against external sources; the
operator operates against the agent's outputs.

This rejection forecloses a fun-sounding demo (the agent uses
Stagehand to do the operator's review work) that would actually be
a category error.

### 12.10 REJECT: AnchorBrowser running in parallel with Browserbase

*(Added 2026-05-23 alongside the AnchorBrowser vendor verdicts.)*

**One provider per layer.** The discipline is codified in the
Daytona integration spec §2 ("one provider per acquisition layer,
swap via adapter") and applies symmetrically here. The same
discipline governs `runtime/db_lock.py` (one writer per substrate
file) and `substrate/dispatch/providers/` (one provider per tier,
with **named** fallback chains — not concurrent dual-vendor).

Running Browserbase and Anchor as parallel concurrent escalation
paths would:

- **Double the TOS surface.** Two policy docs, two outage modes,
  two billing relationships, two DPAs.
- **Force routing logic at `_try_browserbase_escalation`.** "Which
  provider for which URL?" That decision has no principled answer
  — both vendors target the same JS-rendered-SPA failure mode the
  httpx primary can't reach. The binary `fallback_to_browserbase:
  bool` flag is the right shape; a `fallback_to_<vendor>` enum is
  the wrong shape.
- **Create silent-fallback temptation** ("Browserbase failed, try
  Anchor"), which violates spec §14.4 (`Failure is loud:
  BrowserbaseProviderError raises explicitly; no silent fallback
  to a different provider`).

The defensible posture is **mono-vendor with a named Plan B** —
§14.4.1 names AnchorBrowser as that Plan B. If Browserbase fails
the §15.2 acceptance criteria or becomes unavailable, the operator
makes a *single, deliberate, audited* switch — adapter swap, not
concurrent fan-out. Same shape as the dispatch router's
verify-tier fallback (Hermes bridge spec, commit `cd602c9`):
named fallback, not concurrent.

This rejection is reversible only if the underlying substrate
shape changes — e.g., if a future Wedge 4 surface genuinely
benefits from running both vendors against the same page for
cross-validation. That's hypothetical and not in scope today.

---

## 13. Cost, legal, and safety envelope

The numbers below are 2026-Q1 estimates. **Confirm current pricing
before any sprint commit. Re-verify quarterly thereafter.**

### 13.1 Cost model

| Operation | Cost (USD) | Notes |
|---|---|---|
| One `httpx` URL fetch | ~$0.0001 | Bandwidth + electricity only |
| Antiek's own HTML→markdown extract | ~$0 (CPU-only) | Already in `processing/extraction/` |
| One Exa `/search` call (10 results) | ~$0.005 | $5/1k searches |
| One Exa `/contents` call (10 URLs, no summary) | ~$0.005 | $5/1k pages |
| One Exa `/contents` call (10 URLs, with summary) | ~$0.02–0.05 | Summary uses LLM, varies by model |
| One Exa `findSimilar` call | ~$0.001 | $1/1k calls |
| One Browserbase session (1 minute, no Stagehand) | ~$0.10 | Per session-minute, rounded up |
| One Browserbase session (3 minutes, Stagehand-driven) | ~$0.30 + ~$0.005 (LLM calls) | |
| One verifier-tier dispatch call (Grok 4.3 via Hermes) | ~$0.005 | Existing; unchanged by Wedges |

**The asymmetries that drive the verdicts:**
- Exa search ≈ 50× httpx fetch. Cheap enough to be a routine discovery cost.
- Browserbase session ≈ 1000–5000× httpx fetch. Reserved for escalation.

### 13.2 Daily budget caps (default values; configurable)

- `EXA_DAILY_BUDGET_USD`: $5. Sustains ~1k searches/day or ~500 contents calls.
- `BROWSERBASE_DAILY_BUDGET_USD`: $5. Sustains ~25 escalation sessions/day.
- Total acquisition budget cap (sum of Exa + Browserbase + future
  providers): $10/day default. Enforced at `acquisition/search/__init__.py`
  level.

**Cap behavior:** the next call raises a typed
`DailyAcquisitionBudgetExceeded` error. There is no silent throttle,
no silent provider swap. The operator sees the failure.

### 13.3 Legal envelope

- **Exa's TOS:** Exa indexes the public web and licenses access to
  its index. Antiek's use is consistent with their published terms
  (verified 2026-Q1; re-verify before Sprint 18 commit).
- **Browserbase's TOS:** Browserbase provides infrastructure; the user
  is responsible for what they crawl. Antiek's use must respect
  robots.txt and applicable site terms. The wedge specs (especially
  §7.5, §12.7) commit to this.
- **AG MDL / Hachette / Bartz banned-corpus list:** enforced at the
  Sprint 18 retrieval-time gate. Both Exa-sourced and Browserbase-
  sourced URLs flow through the gate before any graph write.
- **GDPR / personal data:** Exa's `category="linkedin profile"` and
  `category="company"` results may surface personal data. Antiek
  operator (single operator pre-Sprint-19) is the data controller.
  Sprint 22 multi-user pivot needs to re-evaluate data-controller
  arrangements before this wedge is exposed to non-operator users.

### 13.4 Safety envelope

- **Exa cannot execute code.** Exa returns text and URLs. Safe.
- **Browserbase executes JavaScript on remote pages.** That's the
  point. Risks:
  - Malicious sites can fingerprint Browserbase sessions and target
    them (e.g. serve a poison page on detection). Mitigation:
    Browserbase's stealth mode is enabled by default; we don't add
    aggressive identifying headers.
  - Browser exploits in the Chromium build could compromise the
    Browserbase session. Mitigation: not our infra; trust
    Browserbase's patching cadence. Sessions are ephemeral and
    isolated per their docs.
  - Cross-site state leakage if sessions are pooled. Mitigation:
    sessions are NOT pooled across investigations or domains by
    default (§7.6, §12.8).
- **Cost-as-DoS.** A bug that loops on `discover(...)` or
  `fetch_via_browserbase(...)` can exhaust budget in minutes. Mitigation:
  hard daily caps + per-call cost logging + weekly reporting (§6.7,
  §13.2).

---

## 14. Risks and mitigations

### 14.1 Discovery-layer pollution

**Risk:** Wedge 1 floods the event log with `DiscoveryProposed`
events; the operator stops paying attention and the audit value
decays.

**Mitigation:**
- Discovery events live in a separate JSONL file from substrate
  events (`~/.antiek/discovery_events/*.jsonl`), not interleaved.
- A discovery-review surface (Sprint 19 work, ties to PostHog Wedge 3
  command palette) lets the operator skim proposals, filter by
  query / domain / score.
- 30-day retention default; older proposals roll up to a summary table.

### 14.2 Doc-id collision via final-url drift

**Risk:** A URL's `final_url` (after redirects) varies across fetches
(some sites change canonical slugs over time). Two fetches via two
sources (Exa + manual paste) of the same logical content might
produce two different `final_url` values and two different
`url_doc_id` hashes.

**Mitigation:**
- `url_doc_id` already uses `final_url`, not `requested_url` — same
  redirect produces the same id.
- Add a `url_alias` table mapping `requested_url → document_id` so
  re-encountering an alias links back to the canonical document.
- Operator-facing alert when a near-duplicate document is created
  (high embedding overlap, different URL); operator can merge.

### 14.3 Exa relevance score is opaque

**Risk:** Exa returns a `relevance_score` per result; using it to
auto-promote (rather than operator review) creates a Goodhart
problem against Exa's ranking model.

**Mitigation:**
- Wedge 1 does NOT auto-promote. Every promotion is operator-mediated
  (or a Wedge-3 verifier-tier call with bounded scope).
- The score is recorded in the event payload but not used for
  ingestion gating.

### 14.4 Browserbase API instability

**Risk:** Browserbase is a startup; SDK breaking changes, pricing
changes, or service incidents will happen.

**Mitigation:**
- Wedge 2 is opt-in per-call. Default behavior unaffected by
  Browserbase outages.
- Pin SDK version in `pyproject.toml`.
- The escalation pattern (httpx primary, Browserbase fallback) means
  losing Browserbase degrades to "low_word_count skip," not to
  total acquisition failure.
- Failure is loud: `BrowserbaseProviderError` raises explicitly; no
  silent fallback to a different provider.
- **Named Plan B exists** — see §14.4.1 below.

### 14.4.1 AnchorBrowser as named Plan B (added 2026-05-23)

If Browserbase fails the §15.2 acceptance criteria, becomes
unavailable, or its pricing / TOS becomes incompatible with
Antiek's operator-only single-operator posture, **AnchorBrowser is
the named alternative escalation vendor**. The adapter seam in
`acquisition/urls/client_browserbase.py` was already designed for
vendor swap:

- `_SessionLike` Protocol with two methods (`connect_url`,
  `close`) — vendor-agnostic.
- Injectable `session_factory: Callable[[], _SessionLike]` — tests
  already substitute it.
- Injectable `page_runner` returning `(html_bytes, final_url,
  status_code)` — vendor's CDP behavior is contained in the
  default runner.

A future `acquisition/urls/client_anchorbrowser.py` is a ~150-LOC
near-mechanical port: same Protocol, same runner shape, different
`_default_session_factory` (Anchor's `anchor.Anchor().sessions.create(...)`
in place of Browserbase's `Browserbase().sessions.create(...)`),
same robots/budget/semaphore plumbing. The closed Literal
`fallback_fetcher: Literal["browserbase"]` in
`FetchFallbackEscalatedPayload` (§7.3) is the only schema surface
that widens — one Pydantic edit + one TS codegen run, schema bump
v9 → v10.

**This is documented now, not coded now.** Per master-spec §16,
pre-building for a hypothetical vendor switch is forbidden. The
Plan-B contract exists at the spec level so a future PR has a
defensible shape to land into without re-litigating the verdict.

**Anchor-specific evidence as of 2026-05-23:**

- *Pricing*: Inconsistent public copy. One page advertises
  $0.05/browser-hour (~120× cheaper than Browserbase's
  $0.10/session-minute); home page advertises $50/month Starter
  with credit/step/instance metering. **Reconcile via direct
  outreach before any production switch.** At Wedge 2 volume
  (capped at ~25 sessions/day per `BROWSERBASE_DAILY_BUDGET_USD=$5`),
  Browserbase's pay-as-you-go-from-$0 dominates either way.
- *Performance*: The only independent benchmark (Browserless
  comparison, 2026-Q1) measured Anchor 6.0× slower on connection,
  1.9× slower on page creation, 2.4× slower on navigation vs the
  reference. For Wedge 2's ~25-sessions/day occasional-fallback
  pattern with 60s+ sessions, 6× connection latency is a non-issue.
  Anchor is the **wrong** primitive for any hypothetical high-
  throughput case (e.g., a future Wedge-4 at scale or the WP-A3
  parallel-fan-out problem from the Daytona spec).
- *Web Action Cache*: Anchor markets record-and-replay for
  deterministic workflow preservation ("80× less tokens"). The
  feature's docs page returned 404 on 2026-05-23. **Treat as
  unverified until docs stabilize.** If verifiable + exportable,
  this would be the strongest Anchor-only differentiator — would
  plug into `tools/golden_traces/` for trajectory replay (the
  Sprint-6 orchestrate.py extraction unlock criterion per the
  Antiek project context). Re-evaluate when documented.
- *OmniConnect (1Password)*: Real ergonomic win over Browserbase's
  raw cookie/localStorage "persistent contexts," but **only
  relevant for Wedge 4** — logged-in browsing is explicitly
  excluded from Wedge 2 (§7.5). Differential only if a Wedge-4
  surface lands AND that surface benefits from delegated 1Password
  auth over operator-managed cookies.

**Trigger conditions for activating Plan B:**

1. Browserbase fails §15.2 unlock criteria (e.g., concurrency cap
   fails to enforce, budget cap fails to fire, the operator's
   JS-rendered-SPA validation refuses to recover content).
2. Browserbase becomes unavailable for ≥7 consecutive days (the
   spec's `HybridSearchDegraded` / `FetchFallbackEscalated` event
   log surfaces the outage rate).
3. Browserbase pricing changes by ≥2× upward (operator-side
   decision, audit-visible via the weekly report).
4. Browserbase's TOS becomes incompatible with Antiek's posture
   (multi-user pivot at Sprint 22+ is the likeliest trigger).

**When a trigger fires:** ship the `client_anchorbrowser.py` port,
bump the `fallback_fetcher` Literal, run §15.2's unlock criteria
against Anchor instead. The mono-vendor invariant holds — Anchor
*replaces* Browserbase; both never run concurrently (§12.10).

### 14.5 The verifier-tier corroboration honeypot (Wedge 3)

**Risk:** As articulated in §8.5 — verifier defers to Exa's "did
agreeing pages exist" signal and stops doing rubric work.

**Mitigation:**
- Calibration eval set (§8.5).
- Rubric weighting MUST keep substrate-grounding primary.
- Wedge 3 acceptance criterion: verifier accuracy on the
  Exa-misleading subset doesn't degrade vs Exa-off baseline.

### 14.6 Wedge sequencing drift

**Risk:** Wedge 1 ships before the Sprint 18 legal gate (sequencing
violation §6.9); restricted content leaks into the graph.

**Mitigation:**
- Sequencing constraint is documented at the wedge level (§6.9).
- The Sprint 18 gate ships first. The Wedge 1 PR includes the gate
  enforcement test — without the gate, the PR fails CI.

### 14.7 Provider lock-in via event-payload shape

**Risk:** `DiscoveryProposedPayload` includes Exa-specific fields
(`provider_response_id`, Exa's `relevance_score` interpretation).
Future providers don't map cleanly.

**Mitigation:**
- `provider` is a `Literal` union — adding a new provider extends
  the union, doesn't break existing events.
- Provider-specific fields are nested under `provider_specific:
  dict[str, Any]` rather than promoted to top-level. The top-level
  fields are the provider-agnostic ones (url, title, query, score).

---

## 15. Unlock criteria for promoting wedges

Each wedge has explicit gates. Crossing them is the ratification event.

### 15.1 Wedge 1 (Exa discovery adapter) unlock criteria

- [ ] Sprint 18 retrieval-time legal gate shipped to production.
- [ ] `DiscoveryProposedPayload` + `DiscoverySelectedPayload` typed in
      `substrate/schemas/events.py`; TS codegen run.
- [ ] `EXA_DAILY_BUDGET_USD` enforcement integration-tested.
- [ ] Operator has run `discover(...)` against a real query on the
      production Exa key, reviewed ≥10 results, ingested ≥3 of them,
      and confirmed the trajectory log captures the discovery → selection
      chain end-to-end.

### 15.2 Wedge 2 (Browserbase escalation fallback) unlock criteria

- [ ] `BROWSERBASE_DAILY_BUDGET_USD` enforcement integration-tested.
- [ ] Concurrency cap (3 sessions) integration-tested.
- [ ] `robots.txt` pre-check verified against one disallowed-domain
      fixture.
- [ ] `FetchFallbackEscalatedPayload` typed and emitted in the
      integration test path.
- [ ] Operator has flipped `fallback_to_browserbase=True` on a known
      JS-rendered SPA fixture and confirmed the recovery + cost
      logging.

**If §15.2 fails to ratify** — Browserbase loses on one or more
criteria — the named Plan B is AnchorBrowser per §14.4.1. The
adapter seam already accommodates the port; the spec contract is
the load-bearing artifact for a future replacement PR. Per §12.10,
the replacement is mono-vendor (Anchor *replaces* Browserbase; no
concurrent dual-vendor escalation).

### 15.3 Wedge 3 (verifier `/contents` lookup) unlock criteria

- [ ] Wedge 1 ratified (above checklist closed).
- [ ] Dispatch-multi-turn tool-call infrastructure exists in
      `substrate/dispatch/` (separate substrate decision, not part of
      this spec).
- [ ] Calibration eval set: ≥20 (claim, expected_result) pairs where
      Exa's `/contents` is known to be misleading.
- [ ] Verifier accuracy with Wedge-3 enabled is ≥ baseline accuracy
      (no degradation on the calibration set).

### 15.4 Wedge 4 (Stagehand structured-data extractor) unlock criteria

- [ ] A specific data surface named, with documented:
  - Volume estimate (pages/day, peak).
  - Per-page cost estimate (Stagehand calls × $0.005 + session-minutes
        × $0.10).
  - Schema design (Pydantic models for the extracted data).
- [ ] Operator-run 100-page spike against the candidate surface;
      cost + reliability data captured.
- [ ] Confirmation that no direct API exists for the same data
      (if an API exists, it dominates Wedge 4).
- [ ] Substrate-write contract: the wedge ingests via
      `acquisition/urls/adapter.ingest_url(...)` where possible; only
      directly mints nodes for structured data with no URL representation.

### 15.5 Wedge 5 (Exa Websets for continuous research) unlock criteria

- [ ] Continuous research mode (`compounding/continuous_research.py`)
      has shipped on a non-Exa baseline (RSS + arxiv polling +
      operator-curated sources) and operated for ≥30 days.
- [ ] Operator can articulate which specific monitoring need the
      non-Exa baseline does NOT cover — i.e. the Webset value-add.
- [ ] Per-Webset cost cap pattern defined and operator-reviewed.

### 15.6 Wedge 6 (full agentic browsing) unlock criteria

All of these. Stringent on purpose.

- [ ] Wedges 1, 2, 3, 4 all shipped and operated for ≥60 days.
- [ ] Documented evidence of ≥10 specific cases where Wedges 1-4
      together could NOT meet a real research need, and free-form
      browsing would have.
- [ ] Trajectory replay viewer (PostHog Wedge 5) shipped — without it,
      Wedge 6 is unobservable.
- [ ] Per-goal cost ceiling pattern designed and operator-reviewed.
      Includes hard timeouts, max-steps caps, and rollback semantics
      when a goal exceeds budget.
- [ ] Undo affordance (PostHog Wedge 4 §8.4) shipped — Wedge 6 takes
      actions; undo must exist for those actions before the role is
      promoted.
- [ ] An operator-graded eval set of ≥30 free-form browsing goals,
      scored against the Wedge 1-4 baseline. Wedge 6 must outperform
      the baseline on at least one principled axis (coverage, cost,
      time-to-result) to justify shipping.

If any criterion fails to ratify, the verdict moves from DEFER to
REJECT permanently.

---

## 16. Sprint placement

| Sprint | Theme | Exa / Browserbase work |
|---|---|---|
| **17** | Interview voice mode + program.md per role | None |
| **18** | Publisher dashboard + Synquery + **retrieval-time legal gate** | Sequencing precondition for Wedge 1. No wedge work this sprint. |
| **18 (late) → 19** | Multi-user pivot start + PostHog Wedge 2 (notebooks) | **Wedge 1 (Exa discovery adapter)** main work. **Wedge 2 (Browserbase escalation)** parallel — independent. |
| **19** | Multi-user / notebooks / command palette (PostHog Wedge 3) | Wedge 1 ratifies. Wedge 2 ratifies. **Wedge 3 (Exa `/contents` for verifier)** scoped IF dispatch-multi-turn tool-call substrate is ready. |
| **20** | Multi-user / payouts / trajectory replay (PostHog Wedge 5) | Wedge 3 main work if scoped. **Wedge 4 (Stagehand for ONE structured-data surface)** main work IF a surface has been ratified. |
| **21-22** | Phase 4 ad inventory | **Wedge 5 (Exa Websets)** consideration if continuous research has operated 30+ days. |
| **22+** | Scale / multi-user-with-team / Phase 4 monetization | Wedge 6 (full agentic browsing) re-evaluation. Possibly REJECT permanently if Wedges 1-5 cover ≥95% of demand. |

**Critical sequencing constraints:**
- Wedge 1 cannot land before the Sprint 18 retrieval-time legal gate.
- Wedge 3 cannot land before Wedge 1 ratifies AND dispatch-multi-turn
  tool-call substrate is ready (separate substrate decision).
- Wedges 4, 5, 6 each have explicit unlock criteria (§15.4-15.6).

**What's NOT on the critical path:**
- Wedge 2 (Browserbase escalation) can ship independent of Wedge 1.
- The discovery-event types in `substrate/schemas/events.py` can land
  ahead of Wedge 1 as a substrate-only PR.

---

## 17. Open questions (genuinely unresolved)

These are the questions this spec does NOT settle. Each requires
operator decision before the wedge it gates lands.

### 17.1 Should Wedge 1 share `acquisition/search/` with future providers (SerpAPI, Tavily, Perplexity), or get its own `acquisition/exa/`?

This spec recommends `acquisition/search/exa/` to anticipate sibling
providers. The alternative (`acquisition/exa/` at the same level as
`acquisition/urls/`) is more parallel to existing acquisition modules
but encodes the assumption that Exa is one of one, not one of many.

**Recommendation:** `acquisition/search/exa/`. The discovery layer
is its own pattern, distinguishable from the source-specific adapters
(arxiv, books, podcasts). Future providers extend it cleanly.

**Operator decision needed before Wedge 1 ships.**

### 17.2 Does Browserbase's persistent context (cookies across sessions) belong in Wedge 2 or only in Wedge 4?

This spec says Wedge 4 only (§7.5). The alternative: Wedge 2 could
optionally accept a persistent context for sites the operator has
logged into. This is more powerful but introduces state per-domain.

**Recommendation:** Wedge 4 only. Wedge 2's mission is "smarter
fetch for the same logged-out URL"; logged-in browsing is a
fundamentally different mode and deserves its own wedge.

**Operator decision needed before Wedge 2 ships.**

### 17.3 Is Exa's `findSimilar` valuable enough to include in Wedge 1, or should it be deferred?

`findSimilar` adds a "I have one good source, find five more like
it" capability. Independently valuable to discovery. But it's a
distinct call shape (URL → URLs, not query → URLs) and adds API
surface.

**Recommendation:** include in Wedge 1 from day one. It's the same
event shape (`DiscoveryProposed` with `query=<originating_url>`), so
no schema cost. Operator-side value is high — easy way to expand a
narrow lead.

**Operator decision needed before Wedge 1 ships.**

### 17.4 Which specific surface justifies Wedge 4 (or does any)?

Listed candidates in §9.1. None ratified. If no surface emerges over
Sprints 18-19, Wedge 4 may simply not ship — defer permanently rather
than build a Stagehand adapter for an imaginary use case.

**Operator decision needed when a candidate surface surfaces, NOT
prospectively.**

### 17.5 Should the discovery layer support multi-provider fan-out (query → Exa + SerpAPI + Tavily simultaneously) from day one?

This spec scopes Wedge 1 to Exa only. Multi-provider fan-out (issue
the same query against multiple providers, merge results) is a
separate decision. Value: redundancy + breadth. Cost: 2-3× per query.

**Recommendation:** single-provider in Wedge 1. The multi-provider
pattern is added when a second provider ships, not preemptively.

**Operator decision needed only when a second provider lands.**

### 17.6 What's the right surface for operator review of `DiscoveryProposed` events?

This spec assumes Sprint 19's PostHog Wedge 3 command palette or
Wedge 2 notebook surface picks up discovery review. Concrete UI
design not in this spec's scope.

**Operator decision needed during Sprint 19 UI work.**

### 17.7 Does Stagehand call dispatch through Antiek's router (preserving the substrate-as-source-of-truth for LLM choices) or through Stagehand's own LLM config?

Stagehand defaults to OpenAI; can be configured to use Anthropic,
OpenRouter, or others. The architectural question: when Stagehand
calls an LLM inside a Browserbase session, should that LLM call go
through Antiek's dispatch router (so the tier system + cost tracking
captures it) or through Stagehand's separate config?

**Recommendation:** Stagehand's own config in Wedge 4. The dispatch
router is for *Antiek role calls*; Stagehand's internal LLM is for
*Stagehand's DOM-decision*. Different concerns. Stagehand's cost is
tracked separately as part of the Browserbase budget.

**Operator decision needed before Wedge 4 ships.**

---

## 18. What to do now

**Two INTEGRATE NOW items**, both Sprint 18-19. They depend on the
Sprint 18 retrieval-time legal gate landing first.

### 18.1 Wedge 1 — `acquisition/search/exa` discovery adapter

The largest single discovery-layer upgrade. ~4 days. Adds the missing
primitive ("the agent can find URLs about a topic") without violating
the substrate-as-source-of-truth invariant. Sequence: legal gate
ships → Wedge 1 ships against the gate → operator-mediated
promotion to ingestion. **Defer until the gate ships.**

### 18.2 Wedge 2 — Browserbase escalation fallback

Narrow, opt-in, ~3 days. Solves the `low_word_count` skip cases that
the operator KNOWS have content (JS-rendered SPAs). Default behavior
unchanged; cost bounded by daily budget cap + concurrency cap +
per-call operator opt-in.

### 18.3 Substrate-only precursor (can land at any time)

`DiscoveryProposedPayload` + `DiscoverySelectedPayload` +
`FetchFallbackEscalatedPayload` types added to
`substrate/schemas/events.py`, with `ActionType` extensions and TS
codegen. ~1 day, independent of any wedge. Lets Wedges 1 and 2
hit the ground typed.

### 18.4 Everything else defers

Wedge 3 (verifier `/contents`): PHASE 2, gated on Wedge 1 + dispatch
tool-call substrate.

Wedge 4 (Stagehand for one structured-data surface): conditional on a
specific surface surfacing. May not ship at all.

Wedge 5 (Exa Websets): DEFER. Continuous research mode must work
without Exa first.

Wedge 6 (full agentic browsing): DEFER, possibly REJECT permanently.
Stringent unlock criteria (§15.6) on purpose.

### 18.5 The nine explicit REJECTs

`§12.1-12.9` close the bait that the headline "give the agent web
access" implies. Exa-as-dispatch, Browserbase-as-dispatch, Browserbase
as default fetcher, Exa-summary as `parameter_extractor`, Exa-answer
as synthesizer, legal-gate bypass, robots/paywall bypass, persistent
investigation sessions, Stagehand against Antiek's own UI. These are
not deferred; they are settled negative.

### 18.6 The principle restated

**The substrate is the moat. Exa and Browserbase are inputs to the
substrate, not substitutes for it.**

Exa makes the discovery layer cheaper and richer. Browserbase makes
the long-tail ingestion path reachable. Both are valuable IF they
flow through `acquisition/urls/adapter.ingest_url(...)` and the typed
event log and the Sprint 18 legal gate. Both are substrate violations
IF they shortcut around those things. Every wedge above is structured
to keep the flow correct; every rejection above closes a shortcut.

The integration is the wedges in §6-§11. The rejections in §12 are
the guardrails. The unlock criteria in §15 are the ratchet. The
verdict on Wedges 1 and 2 (the INTEGRATE NOW pair) lands Sprint
18-19, gated on the legal gate.

---

## Final note for the implementing agent

When this spec conflicts with another, precedence is:

1. `architecture_notes.md` — substrate invariants (never violate).
2. `master-product-spec.md` — product vision + sprint sequencing.
3. `strategy/voice-and-style-discipline.md` — synthesis quality bar.
4. This spec — Exa / Browserbase integration verdicts and wedge
   mechanics.
5. Peer integration specs — conflicts resolved by operator review.

If precedence (1) and any wedge ever conflict — i.e., adopting an Exa
or Browserbase pattern would weaken the substrate-as-source-of-truth
invariant — the substrate wins. The wedges in §6-§11 are the means;
the substrate is the end. **Never substitute the end for the means.**

The discovery layer is new. The escalation pattern is new. Both are
structurally clean only because they preserve the single substrate-
write seam at `acquisition/urls/adapter.ingest_url(...)`. Any
implementation that bypasses that seam is wrong, no matter how
plausible the surface argument.

Borrow ruthlessly from Exa and Browserbase where the primitives fit.
Reject loudly where they don't. Use the wedge unlock criteria to
ratchet — and re-evaluate the rejections (§12) only when the
underlying substrate state changes meaningfully, not because the
headline trends shift.
