# Antiek × Turbopuffer — Hybrid Search Substrate Integration Spec

**Status**: Draft v1, 2026-05-23. Operator: Faisal. **Pricing-verification sharpen pass 2026-05-23 (same day)** revised §1.3 + §11.1: prior draft claimed "<$5/month at operator scale" + "cheapest acquisition-adjacent service"; verified pricing shows a **$64/month Launch tier floor** with no free or hobby tier. §13.1 unlock-criteria win-threshold tightened from "≥10% on ≥60%" to "≥15% on ≥70%" + cost-commitment affirmation, to justify $768/year against $0/year DuckDB cosine baseline.
**Scope**: Decide where turbopuffer (serverless vector + BM25 + hybrid
search infrastructure) integrates into Antiek's retrieval layer,
where it's deferred behind unlock criteria, and which adoption shapes
are explicitly rejected as category errors or substrate violations.
Defensible verdicts, not consensus hedging.
**Predecessor docs** (precedence in this order on conflict):
1. `architecture_notes.md` — substrate commitments (load-bearing).
   Especially §2.1 (typed event log), §2.3 (DuckDB single-writer —
   the only-writer invariant that makes turbopuffer a *secondary
   index*, never a primary store), §7 (schema discipline).
2. `master-product-spec.md` — product vision + sprint sequencing.
   Especially §13.2 (two-graph architecture; the multi-user pivot
   commits DuckDB-per-user-private + DuckLake-shared-public, NOT
   turbopuffer-per-user), §13.9 (federation), §16 (no pre-building
   for hypothetical users), §6 (primary source connection).
3. `strategy/voice-and-style-discipline.md` — synthesis quality bar.
4. Peer integration specs (this spec mirrors the discipline of the
   first):
   - **`integration_exa_browserbase.md`** — closest analog. Same
     wedge-style verdict matrix, same REJECT discipline, same
     spike-before-integrate sequencing. **Read it before this spec
     if you haven't.**
   - `integration_prime_intellect.md`, `integration_autoresearch.md`,
     `integration_posthog.md`, `daytona_integration_spec.md`,
     `rlm_integration_spec.md`.
**Operator quality bar**: intellectual honesty, rigor, defensibility.
Explicit REJECT verdicts where warranted. No "turbopuffer is fast,
ship it" or "Notion uses it so we should too" framings. The right
question is always: *what specific Antiek problem does this primitive
solve, and is it a better solve than what we already have native?*

---

## Honest preamble

This spec is drafted **before** the spike, not after. The Exa &
Browserbase spec was drafted after the operator-stated request "is
it rational to include both Exa and Browserbase or should I just use
one?" — there was a concrete decision driving the analysis.
Turbopuffer is different: there is **no operator-request signal**.
DuckDB cosine has not been observed to fail at the operator's actual
scale, and the value proposition (hybrid BM25 + vector) is
theoretical until measured.

This spec therefore commits to **spike-first sequencing**: Wedge 1
(the only INTEGRATE-NOW candidate) ships only after a 1-day spike
demonstrates measurable improvement over DuckDB cosine on the
operator's actual queries. If the spike fails, every wedge below
moves from `SPIKE-then-INTEGRATE` or `PHASE 2` to permanent `DEFER`
or `REJECT`. The spec exists as substrate scaffolding for that
decision either way — wedges that defer have explicit unlock
criteria; rejections have documented reasoning that future operators
can re-evaluate against if the substrate state changes.

This is also a discipline upgrade over the Exa spec: that spec
landed two INTEGRATE-NOW wedges without first running a spike.
Defensible because the operator named the wedges; turbopuffer
doesn't have that operator-naming. We learn from the prior arc and
front-load the measurement.

---

## Table of contents

1. [What turbopuffer actually is](#1-what-turbopuffer-actually-is)
2. [What turbopuffer is NOT — misreadings to avoid](#2-what-turbopuffer-is-not--misreadings-to-avoid)
3. [The single architectural decision — turbopuffer as secondary index](#3-the-single-architectural-decision--turbopuffer-as-secondary-index)
4. [Mapping turbopuffer primitives to Antiek's substrate](#4-mapping-turbopuffer-primitives-to-antieks-substrate)
5. [Verdict matrix](#5-verdict-matrix)
6. [Wedge 1 — Hybrid search over substrate (SPIKE-first)](#6-wedge-1--hybrid-search-over-substrate-spike-first)
7. [Wedge 2 — Discovery-event search](#7-wedge-2--discovery-event-search)
8. [Wedge 3 — Shared public graph search (multi-user pivot)](#8-wedge-3--shared-public-graph-search-multi-user-pivot)
9. [Wedge 4 — Federation substrate](#9-wedge-4--federation-substrate)
10. [Explicit rejections](#10-explicit-rejections)
11. [Cost, legal, and safety envelope](#11-cost-legal-and-safety-envelope)
12. [Risks and mitigations](#12-risks-and-mitigations)
13. [Unlock criteria for promoting wedges](#13-unlock-criteria-for-promoting-wedges)
14. [Sprint placement](#14-sprint-placement)
15. [Open questions](#15-open-questions)
16. [What to do now](#16-what-to-do-now)

---

## 1. What turbopuffer actually is

Read carefully. The product positions itself as "serverless vector
database" but that's marketing. The substantive offering is **hybrid
search infrastructure**: vector + BM25 + native filters combined per
query against BYO-indexed data.

### 1.1 Hybrid search as the core primitive

A turbopuffer query takes:

- A **vector** (typically ≤1024 dims; bring-your-own embedding
  model — turbopuffer does NOT compute embeddings).
- An optional **BM25 text expression** (full-text query against
  whatever string fields you indexed).
- An optional **filter expression** — string equality, numeric range,
  array contains, datetime range, with AND/OR/NOT composition.

It returns ranked results combining vector similarity + BM25 score +
filter satisfaction. The scoring blend is configurable via an alpha
parameter between 0 (pure vector) and 1 (pure BM25).

**The Antiek-shaped problem class**: "find chunks in my substrate
that are *semantically about X* (vector match) AND *literally
mention term Y* (BM25 grounding) AND *match metadata Z*
(source_tier ≤ 2, published_at > 2024-01-01, document_type =
'web_article')."

Pure cosine (what `substrate/graph/search.py:cosine_similarity_sql`
does today) misses two of three dimensions:

| Dimension | DuckDB cosine | Turbopuffer hybrid |
|---|---|---|
| Vector semantic match | ✓ | ✓ |
| BM25 keyword grounding | ✗ (would need DuckDB FTS, not currently wired) | ✓ |
| Native filter expressions | partial (Python-side filter after cosine ORDER BY) | ✓ (first-class, no scan penalty) |

The asymmetry that drives Wedge 1: there is a measurable class of
queries where cosine misses the literal-keyword anchor that BM25
catches.

### 1.2 Namespaces

Multi-tenant isolation primitive. Each namespace is its own
searchable index with independent storage, schema, and write
guarantees. Common patterns:

- **Per-user**: `users.{user_id}` — isolated per-operator graphs.
  Maps to Sprint 22+ multi-user pivot territory but is REJECT
  per §10.3 (master-spec §13.2 commits per-user DuckDB private
  graphs, not turbopuffer).
- **Per-topic**: `topics.{topic_id}` — operator-curated
  search-spaces. Tractable, low cardinality.
- **Per-investigation**: `investigations.{inv_id}` — high
  cardinality (one per Loop-1 run); cost compounds if not bounded.
- **Cross-cutting**: `substrate.documents`, `substrate.chunks`,
  `substrate.discoveries` — single shared indexes, partitioned by
  filter rather than namespace.

The pattern that fits Wedge 1: one shared `substrate.chunks`
namespace, filtered per-query by `owner_user_id` once multi-user
lands.

### 1.3 Pricing model (verified 2026-05-23 via direct WebFetch of turbopuffer.com/pricing + /docs/pricing-log)

**This section was materially wrong in the prior draft.** Below is
the verified pricing as of 2026-05-23; the "<$5/month at operator
scale" claim and the "cheapest acquisition-adjacent service"
framing in the prior text were both based on incomplete pricing
data and are now revised.

**There is no Turbopuffer free or hobby tier.** The entry tier
("Launch") carries a $64/month minimum usage charge regardless of
actual consumption.

| Tier | Monthly minimum | Notes |
|---|---|---|
| **Launch** | **$64/month** | Entry tier. Community Slack + email support |
| Scale | $256/month | Private Slack, 8-5 support hours |
| Enterprise | ≥$4,096/month + 35% usage premium | 24/7 support, 99.95% uptime SLA |

**Per-unit rates (Launch tier, February 2026 update):**
- **Query rate**: $1/PB queried data (was $5/PB; February 2026
  reduction). 80% marginal discount on 32-128 GB queried; 96%
  marginal discount on >128 GB queried.
- **Minimum billable per query**: 1.28 GB (was 256 MB; February
  2026 increase).
- **Namespace pinning (April 2026)**: GB-hours instead of
  per-query TB-queried pricing. Minimum 64 GB and 10 minutes.
- **Storage, write, read absolute rates**: not on the public
  page. The published pricing page references a calculator; rates
  not extractable here. Operator must visit pricing page to
  estimate specific cost.

**For Antiek's projected substrate at single-operator scale**
(~10k-100k chunks, ~768-dim sentence-transformers vectors, ~50
queries/day):

- The $64/month Launch minimum is the floor — **regardless of
  actual usage at operator scale, the cost is $64/month, or
  $768/year**.
- Per-query cost at the rates above: 50 queries/day × 1.28 GB
  minimum billable × 30 days = 1,920 GB-queries/month. At $1/PB
  ($1 / 1,048,576 GB) = ~$0.002/month — far under the $64 floor.

**The asymmetry — REVISED 2026-05-23**: turbopuffer is **NOT the
cheapest acquisition-adjacent service** at operator scale. With a
$64/month floor regardless of usage:

| Service | Operator-scale monthly cost |
|---|---|
| `httpx` URL fetcher | ~$0 (CPU only) |
| DuckDB `cosine_similarity_sql` | ~$0 (in-process) |
| Exa /search | ~$0-7/month (1k free tier, then $7/1k) |
| Browserbase escalation | ~$0/month (1 browser-hour free tier covers Wedge-2 volume) |
| **Turbopuffer Launch** | **$64/month MINIMUM** |
| Browserbase Developer plan | $20/month |
| Browserbase Startup plan | $99/month |

Turbopuffer's $64/month floor puts it in the same cost class as
Browserbase's paid plans — and Antiek doesn't even need a
Browserbase paid plan at Wedge-2 volume. **Cost IS a constraint
here, not just quality.** The spike (§6.4) must demonstrate
quality improvement worth $768/year against DuckDB cosine's $0/year —
not merely "≥10% improvement on ≥60% of queries" (the prior bar).
See §13.1 below for the tightened unlock criteria.

### 1.4 What's notable about turbopuffer specifically (vs Pinecone, Weaviate, pgvector)

- **Cold-storage-first architecture**. Writes are durable from
  t=0; reads warm-cached on first access. No "spinning up an
  index" overhead like Pinecone serverless pods.
- **Native filters are first-class**. A filter that eliminates
  99% of vectors costs the same as one that keeps them
  (post-filter pruning, not post-rank). pgvector and most others
  filter after ranking — slower.
- **BM25 as a peer to vector**. Hybrid is the default mode, not a
  bolt-on. Weaviate's hybrid is solid; pgvector doesn't have one;
  Pinecone added it later.
- **Production-customer-validated**. Notion (rumored), Cursor — a
  startup with revenue-generating production load, not a research
  toy.
- **Embedded-key model**. The customer's embedding model is
  decoupled from turbopuffer's API. You change embeddings; you
  re-index. You don't have to re-platform.

### 1.5 What both turbopuffer and DuckDB cosine share

Both are **retrieval-layer** services — they index BYO data and
return ranked results. They are NOT acquisition primitives (don't
crawl the web), NOT LLMs (don't generate text), NOT graph operators
(don't traverse edges). They sit *downstream* of
`acquisition/urls/adapter.py` in the data flow.

This framing is load-bearing for §3 below.

---

## 2. What turbopuffer is NOT — misreadings to avoid

These are framings that look plausible but are wrong for Antiek's
state. Each becomes a REJECT in §10 unless explicitly upgraded.

### 2.1 Turbopuffer is NOT a replacement for DuckDB as Antiek's substrate store

The substrate-as-source-of-truth invariant
(`architecture_notes.md` §2.3) commits to DuckDB as the only-writer
substrate. Turbopuffer is a **secondary index** — a denormalized
read-optimized view computed from DuckDB-written canonical data.
The arrow is unidirectional: DuckDB → turbopuffer.

If we let turbopuffer become the primary store (operator queries
it directly without DuckDB authoritative, writes to it directly
bypassing the lock), we lose:

- **ACID writes**. DuckDB has them; turbopuffer's namespace
  consistency model is eventual and read-after-write semantics
  are best-effort.
- **Single-writer discipline**. The
  `runtime/db_lock.connect_write` invariant assumes one writer
  per substrate file. Turbopuffer doesn't fit into that
  abstraction.
- **Substrate replayability**. The typed event log writes through
  DuckDB; the trajectory-as-product invariant (master-spec
  §15.4) breaks if some writes go to a different store.
- **Backup + restore semantics**. DuckDB files back up via
  filesystem snapshot; turbopuffer namespaces back up via
  provider-export which is slower + lossier.

These are not optional. Turbopuffer as primary substrate is REJECT
(§10.1).

### 2.2 Turbopuffer is NOT a dispatch provider

`substrate/dispatch/providers/` is the LLM provider abstraction —
OpenAI-shaped chat-completions adapters that handle prompt +
response + usage tracking. Turbopuffer is a search index. Forcing
it into dispatch overloads the abstraction with two unrelated
shapes. Discovery, dispatch, and retrieval are different concerns
(the Exa & Browserbase spec §3 makes the discovery / ingestion
split load-bearing; the same logic extends here). REJECT (§10.2).

### 2.3 Turbopuffer is NOT a per-user private-graph store

The master-spec §13.2 two-graph architecture commits:
- **Per-user private graphs**: DuckDB-per-user files routed by
  the application layer.
- **Shared public graph**: DuckLake (DuckDB + Postgres catalog).

Replacing per-user DuckDB with per-user turbopuffer namespaces
violates the §13.2 architecture decision. The shared public graph
*could* use turbopuffer as its retrieval index (that's Wedge 3),
but private graphs stay DuckDB. REJECT for private (§10.3).

### 2.4 Turbopuffer is NOT an embedding model

Turbopuffer takes vectors; it doesn't compute them. Antiek's
existing `processing/embedding/embed.py` (sentence-transformers)
computes embeddings; turbopuffer indexes them. The embedding-model
decision is upstream of the turbopuffer decision.

If the operator migrates embedding models (sentence-transformers
→ some larger model), the turbopuffer namespace would need
re-indexing. This is a real cost — re-encoding ~100k chunks +
re-writing to turbopuffer at $5/1M writes ≈ $0.50 in writes plus
the embedding compute. Not catastrophic but not free. See §11.4.

### 2.5 Turbopuffer is NOT a discovery primitive

The Exa & Browserbase spec at §3 makes the discovery vs
ingestion vs retrieval distinction load-bearing:

- **Discovery layer** (Exa, SerpAPI, …): find URLs in the public
  web. Returns URLs the operator might want.
- **Ingestion layer** (`acquisition/urls/adapter.py` + optional
  Browserbase escalation): turn URLs into bytes + substrate
  rows.
- **Retrieval layer** (DuckDB cosine today; turbopuffer hybrid
  in Wedge 1): search BYO-indexed substrate data.

Putting turbopuffer in the discovery layer is a category error.
It doesn't crawl the web; it indexes data the operator already
owns. REJECT (§10.6).

### 2.6 Turbopuffer is NOT a free upgrade

DuckDB cosine works today. The operator has not complained about
it. Adding turbopuffer:

- Introduces an **external SaaS dependency** (provider outages
  affect search; the substrate must degrade gracefully).
- Adds a **sync layer** (DuckDB writes → turbopuffer writes) with
  consistency lag. Reads against turbopuffer can return stale
  data relative to a just-completed DuckDB write.
- Adds a **new failure mode** — turbopuffer outage degrades
  search to "stale results" or, if the wedge implements a
  fallback, to "DuckDB cosine."
- Adds a **monthly fee** (~$5-10/month at current scale; scales
  with namespace size and query rate).
- Adds **developer cognitive load** — one more system to reason
  about during debugging.

These are not show-stoppers but they're not free either. The
spike (§6.4) must justify these costs against a measurable
quality improvement. If the spike doesn't show ≥60% of operator
queries getting a better result from hybrid than from cosine, the
costs aren't justified.

### 2.7 Turbopuffer is NOT a substitute for graph operations

Antiek's substrate has graph queries beyond pure search:

- **Traversal** (`substrate/graph/traverse.py`) — multi-hop edge
  walks.
- **Cross-graph similarity** (`substrate/cross_graph/`) — graph-
  shaped questions, not bag-of-vectors questions.
- **Constraint satisfaction** (`middleware/constraint_check/`) —
  domain-specific predicate evaluation.

None of these are turbopuffer-shaped. Turbopuffer is a flat-index
search; graph traversal stays in DuckDB. The wedges below scope
turbopuffer to its actual fit (chunk + node + discovery-event
search) — not graph ops.

### 2.8 Turbopuffer is NOT a federation primitive without explicit design

The federation use case (master-spec §13.9, cross-instance search)
is tempting because turbopuffer namespaces could host per-instance
shards. But the federation design (consent model, citation flow,
trust boundaries, sybil resistance) is upstream of the technology
choice. Federation in 2026 may use turbopuffer, may use something
else; Wedge 4 below treats this as DEFER until the federation
design lands.

---

## 3. The single architectural decision — turbopuffer as secondary index

> **Turbopuffer is a secondary read-optimized index. DuckDB stays
> the only-writer substrate. The arrow is unidirectional, the
> consistency is eventual, the fallback is always cosine.**

This decision drives every wedge below.

```
┌──────────────────────────────────────────────────────────────────┐
│  CANONICAL SUBSTRATE (single-writer DuckDB)                      │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ substrate/graph/schema.py                EXISTING         │   │
│  │   documents, chunks, nodes, edges                         │   │
│  │   url_alias, discovery_cache, discovery_summary           │   │
│  │   (all writes through runtime/db_lock.connect_write)      │   │
│  └───────────────────────────────────────────────────────────┘   │
│                          │                                        │
│                          ▼   one chunk write per chunk            │
│                              (eventually consistent sync)         │
│                                                                   │
│  SECONDARY INDEX (turbopuffer, read-optimized)                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ substrate/graph/turbopuffer_index.py     NEW (Wedge 1)    │   │
│  │   namespace: substrate.chunks                             │   │
│  │   indexed: chunk_id, document_id, embedding (BYO),        │   │
│  │            text (BM25), section_path, token_count,        │   │
│  │            owner_user_id, source_tier (filter),           │   │
│  │            document_type, published_at                    │   │
│  │   served via: substrate/graph/hybrid_search.py            │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

**Three consequences every wedge honors:**

1. **Substrate writes go through DuckDB first.** Turbopuffer
   sync happens after the DuckDB transaction commits. A failed
   turbopuffer write does NOT block the substrate write — the
   sync layer records the failure and retries on the next
   reconciliation pass.

2. **Reads fall back to cosine on turbopuffer failure.** The
   `hybrid_search` function consults turbopuffer; on any
   timeout / 5xx / SDK exception, it falls back to
   `cosine_similarity_sql` and emits a typed event recording
   the degradation. Wedge availability never depends on
   turbopuffer availability.

3. **The substrate-as-source-of-truth invariant holds.** Every
   chunk in turbopuffer traces back to a chunk in DuckDB. If
   the two ever diverge, DuckDB wins. The reconciliation pass
   (§6.6) closes drift by re-indexing missing-from-turbopuffer
   chunks and deleting orphan-in-turbopuffer chunks that have
   been removed from DuckDB.

If a future wedge proposes violating this split (e.g. "write
directly to turbopuffer skipping DuckDB"), the wedge is
**rejected on architecture grounds before any cost/value
analysis**. The split is prior to the wedge selection — same
discipline as the Exa & Browserbase spec §3.

---

## 4. Mapping turbopuffer primitives to Antiek's substrate

| Turbopuffer primitive | Closest Antiek analog | Mapping cleanliness | Layer |
|---|---|---|---|
| Hybrid query (vector + BM25 + filter) | `cosine_similarity_sql` in `substrate/graph/search.py` | **Strong analog — measurable upgrade if BM25 catches anything cosine misses.** Wedge 1 | Retrieval |
| Vector-only query | `cosine_similarity_sql` | Marginal — cosine works at current scale. Pure-vector turbopuffer beats cosine only on latency at scale. | Retrieval |
| BM25-only query | DuckDB FTS exists but is not wired into substrate/graph/search.py | Weak — operator hasn't asked for full-text search; cosine has covered most queries | Retrieval |
| Native filter expressions | Python-side filter after cosine ORDER BY | **Strong analog.** Filters at scan time are cheaper than filter-after-rank. Wedge 1 incorporates | Retrieval |
| Namespaces (per-user) | Per-user DuckDB files (master-spec §13.2 commitment) | **Anti-mapping — master-spec commits to DuckDB-per-user.** REJECT §10.3 | Retrieval / multi-user |
| Namespaces (per-topic) | None — operator currently filters by topic via DuckDB column | Medium — namespace-per-topic adds isolation but high-cardinality topics fragment the warm cache | Retrieval |
| Namespaces (cross-cutting `substrate.chunks`) | Single DuckDB chunks table | Strong analog. Wedge 1's namespace shape | Retrieval |
| BYO embeddings | `processing/embedding/embed.py` (sentence-transformers) | Compatible — turbopuffer takes the same float vectors Antiek already computes | Compute / retrieval boundary |
| Cold storage architecture | DuckDB in-memory + on-disk | Different ops model — turbopuffer's cold storage is cheaper per-GB but adds per-read cost | Retrieval / cost |
| Multi-region replication | None — DuckDB is single-region by default | Speculative — Antiek hasn't expanded beyond one operator's machine; multi-region is Sprint 25+ | Substrate scale |
| Federation across customers | None — federation is master-spec §13.9 territory, not yet built | Anti-mapping until federation design lands. Wedge 4 DEFER | Substrate / federation |
| Custom scoring functions | None | Premature — cosine returns a float; the operator hasn't asked for custom scoring shapes | Retrieval / config |

**The cleanest wins** are Wedge 1 (hybrid search over substrate
chunks). The cleanest medium-confidence wins are Wedge 2
(discovery-event search) and Wedge 3 (shared public graph at
Sprint 22+ scale). The high-risk shape is Wedge 4 (federation),
deferred until federation design lands.

---

## 5. Verdict matrix

| Wedge | What it is | Verdict | Sprint |
|---|---|---|---|
| **Wedge 1: Hybrid search over substrate chunks** | Index DuckDB chunks into a turbopuffer `substrate.chunks` namespace; expose `hybrid_search(query, *, k, filter, alpha)` in `substrate/graph/hybrid_search.py`. Cosine stays as fallback when turbopuffer is unreachable | **SPIKE first; then INTEGRATE NOW if spike wins on the operator's actual queries** | 18-19 (spike: ~1 day; wedge: ~3 days) |
| **Wedge 2: Discovery-event hybrid search** | Index `DiscoveryProposedPayload` events into a `substrate.discoveries` namespace so the Sprint 19 discovery-review UI can do BM25+vector search across "what URLs has the agent considered" | **PHASE 2** — gated on Wedge 1 ratification + Sprint 19 discovery-review surface landing | 19-20 |
| **Wedge 3: Shared public graph search (multi-user pivot)** | Multi-user pivot's shared public graph (master-spec §13.2) uses turbopuffer namespaces for cross-user retrieval. DuckLake holds the canonical store; turbopuffer is the read index | **DEFER** — gated on multi-user pivot shipping (Sprint 22+) | 22+ |
| **Wedge 4: Federation substrate** | Cross-instance vector search (master-spec §13.9) uses turbopuffer namespaces with per-instance shards | **DEFER — possibly REJECT permanently** | 25+ |
| **Use turbopuffer as primary substrate store** | Operator writes to turbopuffer directly; DuckDB becomes secondary | **REJECT** — substrate-as-source-of-truth invariant | — |
| **Use turbopuffer as a dispatch provider** | Add turbopuffer to `substrate/dispatch/providers/` | **REJECT** | — |
| **Use turbopuffer for per-user private graphs** | Replace DuckDB-per-user with turbopuffer namespaces per user | **REJECT** — conflicts with master-spec §13.2 | — |
| **Synchronous sync (block writes until turbopuffer ack)** | DuckDB write waits for turbopuffer write before returning | **REJECT** — turbopuffer outage shouldn't break ingestion | — |
| **Wholesale cosine replacement without spike data** | Drop `cosine_similarity_sql` before measuring | **REJECT** — pre-build forbidden by master-spec §16 | — |
| **Use turbopuffer for the discovery layer** | Turbopuffer-against-public-web | **REJECT** — different layer (turbopuffer is BYO data; Exa is in the discovery role) | — |
| **Use turbopuffer to host the embedding model** | Embedding compute moved to turbopuffer's hosted endpoint | **REJECT** — turbopuffer doesn't host embedding models; this is a category error | — |
| **Re-encode embeddings without explicit re-index plan** | Migrate embedding model without reindexing turbopuffer | **REJECT** — invalidates the index, returns garbage | — |
| **Use turbopuffer as the legal-gate enforcement point** | Filter banned-corpus URLs at turbopuffer query time | **REJECT** — the legal gate sits at the SQL-WHERE level (Exa spec §6.9 binding); turbopuffer is downstream | — |

---

## 6. Wedge 1 — Hybrid search over substrate (SPIKE-first)

The first INTEGRATE-candidate. Detailed because it sets the
retrieval-layer contract every subsequent turbopuffer wedge
inherits.

### 6.1 What it does

Adds `substrate/graph/turbopuffer_index.py` + `substrate/graph/hybrid_search.py`:

```
substrate/graph/
  schema.py                     # EXISTING — DuckDB authoritative store
  search.py                     # EXISTING — cosine_similarity_sql (stays as fallback)
  turbopuffer_index.py          # NEW — DuckDB → turbopuffer sync layer
  hybrid_search.py              # NEW — hybrid_search() + cosine fallback
  reconcile.py                  # NEW — periodic DuckDB ↔ turbopuffer reconciliation
```

**Operator API** (the seam other code calls):

```python
from substrate.graph.hybrid_search import hybrid_search, HybridSearchResult

results: list[HybridSearchResult] = hybrid_search(
    query="quantum error correction recent advances",
    k=10,
    filter={
        "source_tier": {"$lte": 2},          # Tier 1 or 2 only
        "published_at": {"$gte": "2024-01-01"},
        "owner_user_id": "__operator__",     # for forward-compat
    },
    alpha=0.5,                                # 0=pure vector, 1=pure BM25
    fallback_to_cosine=True,                  # default True
)
# results[i].chunk_id, .score, .text, .document_id, .source_tier
```

### 6.2 The data flow, step by step

**Write path** (driven by `acquisition/urls/adapter.ingest_url`
on every successful chunk write):

1. DuckDB write completes (canonical write through
   `runtime/db_lock.connect_write`).
2. **After** the DuckDB transaction commits, a sync hook calls
   `turbopuffer_index.index_chunk(chunk_id, document_id, text,
   embedding, ...metadata)`.
3. The sync hook writes to turbopuffer's `substrate.chunks`
   namespace. Failure is non-fatal — the substrate write
   already succeeded. The failure is recorded as a
   `TurbopufferSyncFailed` event for the reconciliation pass to
   pick up.
4. Reconciliation runs (cron, or operator-triggered) to close
   drift: re-write missing chunks, delete orphans.

**Read path**:

1. Caller invokes `hybrid_search(query, k, filter, alpha)`.
2. The function encodes `query` to a vector via the existing
   `processing/embedding/embed.py` provider.
3. Sends the (vector, BM25 query string, filter) to turbopuffer.
4. On any timeout / 5xx / SDK exception, falls back to
   `cosine_similarity_sql` against DuckDB and emits a
   `HybridSearchDegraded` event with the failure reason. Caller
   doesn't see the difference except in latency.
5. On success, returns typed `HybridSearchResult` rows.

### 6.3 New event types

Add to `substrate/schemas/events.py`:

```python
class TurbopufferSyncFailedPayload(_PayloadBase):
    """A chunk write succeeded in DuckDB but the turbopuffer
    sync failed. Recorded so the reconciliation pass can pick
    it up. Spec §6.2 — substrate write does NOT block on
    turbopuffer."""
    chunk_id: str
    document_id: str
    failure_reason: Literal[
        "timeout", "5xx", "auth", "rate_limit", "unknown",
    ]
    retry_count: int = 0

class HybridSearchDegradedPayload(_PayloadBase):
    """The hybrid_search path fell back to cosine because
    turbopuffer was unavailable. Audit-visible so the operator
    can see how often degradation happens."""
    query_hash: str        # sha256 of query[:200]
    fallback_reason: Literal[
        "timeout", "5xx", "auth", "rate_limit",
        "namespace_missing", "unknown",
    ]
    cosine_result_count: int

class HybridSearchReconciledPayload(_PayloadBase):
    """The reconciliation pass closed substrate-vs-turbopuffer
    drift. Emitted once per pass."""
    chunks_in_substrate: int
    chunks_in_turbopuffer: int
    missing_from_turbopuffer: int  # re-indexed
    orphans_in_turbopuffer: int    # deleted
    pass_duration_seconds: float
```

Update `ActionType` enum:

```python
TURBOPUFFER_SYNC_FAILED        = "turbopuffer.sync.failed"
HYBRID_SEARCH_DEGRADED         = "hybrid_search.degraded"
HYBRID_SEARCH_RECONCILED       = "hybrid_search.reconciled"
```

Bump `EVENT_SCHEMA_VERSION` and update TS codegen at
`tools/codegen/emit_types.py` so frontend search surfaces can
render these.

### 6.4 The spike that gates this wedge

**Before** any of §6.1-§6.3 ships, run a 1-day spike:

1. Build a throw-away `spike_turbopuffer.py` (not committed) that:
   - Indexes ~1k randomly-sampled chunks from the operator's
     production substrate into a turbopuffer namespace.
   - Reads them back via hybrid + filter.
2. Operator hand-curates **20 queries** representing real
   research questions they've asked or wished they could ask.
   For each, grade the current `cosine_similarity_sql` top-10
   on relevance (0-3 scale per result, score = sum).
3. Run each query against turbopuffer's hybrid mode. Grade the
   top-10 the same way.
4. Compare:
   - **Spike wins** if hybrid scores ≥10% higher than cosine on
     ≥60% of the 20 queries.
   - **Spike loses** if hybrid scores ≤cosine on ≥50% of
     queries.
   - **Spike inconclusive** (between those) → either expand the
     query set to 50 and re-run, or DEFER.

**Spike data dictates the verdict.** If the spike wins, Wedge 1
ships (~3 days of work, detailed in §6.5). If the spike loses,
this entire wedge moves to permanent REJECT and the spec at §10
gains a new entry "REJECT turbopuffer Wedge 1 on insufficient
quality gain (2026-MM-DD spike data)."

### 6.5 Implementation sequence (post-spike, if green)

~3 days of focused work:

- **Day 1** — Schema additions (events.py + tools/codegen) +
  reconciliation table in substrate. ~half a day. New tests:
  payload roundtrip, action types in union.
- **Day 1.5** — `turbopuffer_index.py` write path. Lazy SDK
  import. Sync function called by `ingest_url`. Failure recorded
  as event. ~half a day.
- **Day 2** — `hybrid_search.py` read path. Encode query →
  hybrid call → fallback to cosine on any failure → typed
  results. ~1 day.
- **Day 2.5** — Reconciliation pass (`reconcile.py`). Walks
  DuckDB chunks, compares to turbopuffer namespace, re-indexes
  drift. Operator-callable CLI subcommand. ~half a day.
- **Day 3** — Tests + README + operator validation. ~1 day.

### 6.6 Reconciliation

Per §3 architecture, turbopuffer is eventually consistent.
Reconciliation closes drift in two cases:

1. **Missing from turbopuffer**: chunk exists in DuckDB but the
   sync failed (TurbopufferSyncFailedPayload was emitted). Re-
   index from DuckDB.
2. **Orphan in turbopuffer**: chunk no longer in DuckDB (deleted
   or never written) but still in turbopuffer. Delete from
   turbopuffer.

Reconciliation runs:

- Operator-triggered: `python -m substrate.graph.reconcile`
- Periodic (optional, configurable): every N hours via the
  operator's cron / launchd
- Auto-triggered: after a `TurbopufferSyncFailedPayload` event
  count exceeds a threshold (default 100 unprocessed failures)

The pass emits exactly one `HybridSearchReconciledPayload` so
the audit trail shows when drift was closed.

### 6.7 Authentication and configuration

- **Environment variable**: `TURBOPUFFER_API_KEY`. Never aliased
  to other services' keys (silent misrouting is worse than loud
  failure — same discipline as Exa spec §6.4).
- **Default base URL**: `https://api.turbopuffer.com`. Override
  via constructor for tests (`httpx.MockTransport`).
- **Default timeout**: 5s (reads should be fast; long timeouts
  mask outage signals). Operator can override per-call.
- **Retry policy**: 429 and 5xx retried with exponential
  backoff up to 3 attempts. 4xx other than 429 raises
  immediately (configuration error).
- **Feature flag**: `ANTIEK_USE_TURBOPUFFER_SEARCH=1` enables
  the hybrid path; default off until Wedge 1 ratifies. When
  off, every `hybrid_search` call falls through to cosine.

### 6.8 Cost discipline

Per the Exa & Browserbase spec §13.2 precedent: the combined
acquisition-layer budget cap
(`acquisition/search/__init__.assert_total_budget_ok`) is for
DISCOVERY costs. Retrieval-layer costs are separate.

This wedge adds:

- `TURBOPUFFER_DAILY_BUDGET_USD` (default $5; configurable). A
  hard-stop on the next `hybrid_search` call after threshold;
  raises `TurbopufferBudgetExceeded`.
- Per-call cost in the event payload's
  `cost_usd_estimate` field (HybridSearchDegradedPayload
  records cost regardless of whether turbopuffer or cosine
  served the result).
- Roll-up cost reporting via the existing weekly_report.py
  §7 "Acquisition cost" section, extended with a turbopuffer
  sub-row.

### 6.9 What this wedge does NOT do

- Does NOT write to DuckDB. The substrate write path is
  unchanged; this wedge adds a downstream consumer.
- Does NOT replace `cosine_similarity_sql`. Cosine stays as
  fallback for turbopuffer outages.
- Does NOT add a multi-tenant namespace pattern. One namespace
  per operator (`substrate.chunks`) until multi-user pivot.
- Does NOT change embedding model. Existing
  sentence-transformers vectors are indexed as-is.
- Does NOT take ownership of legal-gate enforcement. The
  Sprint 18 SQL-WHERE gate stays the source of truth; the
  hybrid_search filter can additionally narrow by
  `legal_gate_status` but cannot replace the gate's
  authoritative refusal.
- Does NOT support delete-by-document-id at first ship.
  Operator-triggered reconciliation handles deletions; per-doc
  immediate deletion is a follow-up.

### 6.10 Acceptance criteria

- `hybrid_search(query, k=10)` returns ≥1 result against a
  substrate populated with ≥10 chunks.
- Sync layer writes to turbopuffer within 5s of every DuckDB
  chunk insert (in the same process; cron-based reconciliation
  catches anything missed).
- Turbopuffer outage (simulated via MockTransport returning 503)
  triggers fallback to `cosine_similarity_sql` and emits exactly
  one `HybridSearchDegradedPayload`.
- Reconciliation pass closes drift: induced a TurbopufferSyncFailed
  event, then reconciliation re-indexes the missing chunk;
  follow-up search returns it.
- Daily budget cap (`TURBOPUFFER_DAILY_BUDGET_USD`) triggers
  `TurbopufferBudgetExceeded` on the next call after threshold.
- Operator has run `hybrid_search(...)` against a real
  substrate, compared the top-10 to cosine's top-10, and
  confirmed the trajectory log captures the
  `HybridSearchDegraded` events during induced outages.

### 6.11 Estimated effort

- Spike: ~1 day (operator + assistant)
- If spike wins: ~3 days of focused implementation per §6.5

If the spike loses, total effort is ~1 day (the spike) plus the
documented REJECT decision. That's the spike's value — capping
the loss when the answer is "no."

### 6.12 Sequencing constraint

**Wedge 1 cannot ship before the spike.** Without the spike's
data, the wedge is pre-building per master-spec §16 ("no
pre-building for hypothetical users"). The spike is the
operator's actual users' query data — it's the *only* user-
demand signal available.

If the operator wants to skip the spike, they're explicitly
overriding the master-spec §16 discipline. Defensible if they
have a strong prior; not defensible by default.

---

## 7. Wedge 2 — Discovery-event hybrid search

PHASE 2 — depends on Wedge 1 ratification and the Sprint 19
discovery-review UI surface landing per the Exa & Browserbase
spec §14.1.

### 7.1 What it does

Index `DiscoveryProposedPayload` events into a turbopuffer
`substrate.discoveries` namespace so the discovery-review UI
can search across "what URLs has the agent considered for this
topic?" with hybrid (BM25 + vector + filter).

Search shape:

```python
results = hybrid_search_discoveries(
    query="papers about quantum error correction in 2025",
    filter={"investigation_id": {"$in": ["inv-1", "inv-2"]},
            "suggested_tier": {"$lte": 3}},
    k=20,
)
# Each result: discovery_id, url, title, query (the original),
#              provider, suggested_tier, relevance_score
```

### 7.2 Why this is PHASE 2

Three preconditions:

1. **Wedge 1 must ship and ratify first.** The sync layer +
   fallback semantics + reconciliation pass + budget plumbing
   are all built once for Wedge 1; building them twice is waste.
2. **Discovery-review UI surface must land.** Per Exa &
   Browserbase spec §14.1, this surface ties to "Sprint 19
   work, PostHog Wedge 3 command palette." Until the UI exists,
   Wedge 2 has no consumer.
3. **30-day rollup pattern must be respected.** Per Exa spec
   §14.1, discovery events older than 30 days are rolled up
   into `discovery_summary`. Wedge 2's turbopuffer index needs
   the same retention — index the live 30-day window only;
   rolled-up summaries don't go to turbopuffer.

### 7.3 Substrate-write contract

This wedge does NOT change the discovery event flow:
- `DiscoveryProposedPayload` continues to write to
  `~/.antiek/discovery_events/*.jsonl` (Exa spec §14.1).
- A NEW sync hook fires after the JSONL write, indexing into
  `substrate.discoveries`.
- Rollup truncates the JSONL AND removes the corresponding
  turbopuffer rows in one atomic-ish pass.

### 7.4 What this wedge does NOT do

- Does NOT replace the discovery_events JSONL files. JSONL is
  the audit-of-record; turbopuffer is the search index.
- Does NOT index VerifierLookupPayload events (different shape;
  different operator surface). Could be a Wedge 2.5 if demand
  arises.
- Does NOT change the rollup behavior. Rolled-up summaries
  remain in `discovery_summary` only; not in turbopuffer.

### 7.5 Unlock criteria

See §13.2.

---

## 8. Wedge 3 — Shared public graph search (multi-user pivot)

DEFER — gated on the multi-user pivot shipping (Sprint 22+ per
master-spec §13.2).

### 8.1 What it is

The master-spec §13.2 two-graph architecture commits:
- Per-user private graphs: DuckDB-per-user (REJECT for turbopuffer
  per §10.3).
- Shared public graph: DuckLake (DuckDB + Postgres catalog) for
  authoritative storage.

Wedge 3 adds turbopuffer as the **read index** for the shared
public graph. Sprint 22+ cross-user search reads from turbopuffer
namespaces partitioned by topic.

### 8.2 Why DEFER

- **Multi-user pivot hasn't shipped.** Master-spec §13.2 commits
  Sprint 22+. Building Wedge 3 before the pivot is pre-building
  per master-spec §16.
- **Cost surface is unknown.** Cross-user query rates depend on
  the number of users + their query patterns. Operator has no
  data to project; estimate would be speculation.
- **The "shared public graph" itself is a Sprint 22+
  deliverable.** No data to index yet.

### 8.3 What CAN happen during defer

The discovery-events namespace pattern from Wedge 2 generalizes
to the shared public graph. When Sprint 22+ multi-user lands,
the substrate writes new public-graph chunks; the sync layer
(reused from Wedge 1) indexes them into a
`shared.public_graph.chunks` namespace; cross-user search uses
hybrid the same way Wedge 1 does for the operator's private
graph.

The shape carries over. The implementation is mostly already
written by Wedge 1.

### 8.4 Unlock criteria

See §13.3.

---

## 9. Wedge 4 — Federation substrate

DEFER, possibly REJECT permanently. This is the most-speculative
wedge.

### 9.1 What it would be

Master-spec §13.9 mentions federation: multiple Antiek instances
exposing their graphs to each other under explicit consent
contracts. Cross-instance search would need a substrate that
isn't local-DuckDB-only.

Wedge 4 would make turbopuffer the federation substrate: each
instance writes its consenting-to-share public-graph embeddings
to a shared turbopuffer; cross-instance queries are turbopuffer
reads with per-instance filter expressions.

### 9.2 Why DEFER

Multiple compounding reasons:

- **Federation design hasn't landed.** Consent model, citation
  flow, trust boundaries, sybil resistance, dispute resolution —
  none of these are specified. The technology choice (turbopuffer
  vs. something else) is downstream of the design decisions.
- **No federation users.** Master-spec §13.9 is forward-looking;
  there are zero federated instances today.
- **Cost is unbounded.** Cross-instance search frequency depends
  on the federation's design (push vs. pull, who-pays-for-reads,
  rate limiting). Until those are decided, cost projection is
  speculation.
- **Sprint 25+ at earliest.** Three sprints after the multi-user
  pivot, per master-spec sprint sequence.

### 9.3 Why possibly REJECT permanently

If federation never ships (or ships with a different substrate
choice), Wedge 4 has no demand. The hypothesis is that federation
is a Sprint 25+ feature that may simply not happen — Antiek's
product strategy may converge on single-instance scaling rather
than cross-instance federation. The Sprint-25+ window is far
enough out that "we may never need this" is a defensible read.

### 9.4 Unlock criteria

See §13.4. They are stringent.

---

## 10. Explicit rejections (don't re-litigate)

Stated once. The verdicts are settled. Re-open only if the
underlying substrate or product state changes meaningfully.

### 10.1 REJECT: Turbopuffer as primary substrate store

The substrate-as-source-of-truth invariant (architecture_notes
§2.3) commits DuckDB as the only-writer substrate. Making
turbopuffer primary loses ACID writes, single-writer discipline,
substrate replayability, and clean backup/restore. **Stated
explicitly because the question will be asked**: "Turbopuffer
is faster + cheaper + simpler; why not just use it for
everything?" Because the substrate exists to be replayable +
auditable + recoverable, and turbopuffer is none of those.
Period.

### 10.2 REJECT: Turbopuffer as a dispatch provider

`substrate/dispatch/providers/` is the LLM provider abstraction —
OpenAI-shaped chat-completions. Turbopuffer is a search index;
no shape match. Same rejection logic as the Exa & Browserbase
spec §12.1.

### 10.3 REJECT: Turbopuffer for per-user private graphs

Master-spec §13.2 two-graph architecture commits per-user
DuckDB. Replacing per-user DuckDB with per-user turbopuffer
namespaces violates that architecture decision. Wedge 3 covers
the **shared public graph** as a turbopuffer index; private
graphs stay DuckDB.

### 10.4 REJECT: Synchronous sync (block writes until turbopuffer ack)

Per §3 architecture, turbopuffer is eventually consistent.
Forcing the substrate's DuckDB write to block on a turbopuffer
write means turbopuffer outages stop the substrate cold. That
violates the "secondary index" framing — secondary indexes
should NEVER gate primary writes. Sync is fire-and-forget; the
reconciliation pass closes drift.

### 10.5 REJECT: Wholesale cosine replacement without spike data

Master-spec §16 forbids pre-building for hypothetical users.
Removing `cosine_similarity_sql` before the spike validates
hybrid is "improvement for hypothetical query workload." The
spike (§6.4) is the operator's actual users' data; until it
ratifies hybrid, cosine stays.

### 10.6 REJECT: Turbopuffer for the discovery layer

The Exa & Browserbase spec at §3 separates discovery (Exa) from
ingestion (`acquisition/urls/`) from retrieval (DuckDB / now
turbopuffer Wedge 1). Turbopuffer-against-public-web is a
category error — turbopuffer indexes BYO data; it doesn't crawl.
Exa is in the discovery role.

### 10.7 REJECT: Turbopuffer as the embedding model host

Turbopuffer takes vectors; it doesn't compute them. Asking
turbopuffer to host an embedding model is a category error.
Antiek's existing `processing/embedding/embed.py` stays the
embedding compute layer.

### 10.8 REJECT: Re-encoding embeddings without explicit re-index plan

Migrating the embedding model invalidates every vector in
turbopuffer. Cosine-based search degrades gracefully (mismatched
embeddings return garbage but with same shape); turbopuffer's
hybrid returns garbage too. Without an explicit re-index plan
the operator's queries silently return wrong results. The
operator must trigger a re-index pass *before* switching the
embedding model.

### 10.9 REJECT: Turbopuffer as the legal-gate enforcement point

The Exa & Browserbase spec at §6.9 binds the legal gate to
SQL-WHERE level inside `substrate/legal_gate/`. Turbopuffer is
downstream; banned-corpus refusal happens at ingestion (before
DuckDB write) or query-time (`legal_gate.check_document` before
returning chunks). Putting the gate in turbopuffer means a
turbopuffer outage allows banned content to surface through the
fallback cosine path. The gate must apply on every read path,
turbopuffer included; turbopuffer is not the gate's enforcement
point.

### 10.10 REJECT: Per-user namespaces before multi-user pivot

Building per-user turbopuffer namespaces today (Sprint 17-21,
single operator) is pre-building for hypothetical users.
Master-spec §13.4: multi-user is Sprint 22+. Wedge 3 covers
this when the pivot lands; until then one shared
`substrate.chunks` namespace.

### 10.11 REJECT: Custom scoring functions

Turbopuffer supports custom scoring expressions. Antiek's
operator has not asked for them. Adding custom-scoring complexity
without a demand signal is the kind of pre-build master-spec §16
forbids. The default hybrid (alpha-blended BM25 + vector) is
sufficient until operator demand surfaces.

### 10.12 REJECT: Turbopuffer for graph traversal

Graph traversal (`substrate/graph/traverse.py`) is not turbopuffer-
shaped — it's multi-hop edge walks against a graph schema.
Turbopuffer is flat-index search. Don't try to model traversal in
turbopuffer; keep traversal in DuckDB.

---

## 11. Cost, legal, and safety envelope

Numbers below are 2026-Q2 estimates. **Confirm current pricing
before any sprint commit. Re-verify quarterly thereafter.**

### 11.1 Cost model (revised 2026-05-23 via verified pricing fetch)

**This section was materially wrong in the prior draft. Revised.**

| Operation | Cost (USD) | Notes |
|---|---|---|
| DuckDB `cosine_similarity_sql` | $0 | CPU-only, in-process |
| Turbopuffer Launch tier | **$64/month MINIMUM**, regardless of usage | Entry tier. No free or hobby tier exists. |
| Turbopuffer Scale tier | $256/month minimum | Private Slack + 8-5 support |
| Turbopuffer Enterprise tier | ≥$4,096/month + 35% usage premium | 24/7 + 99.95% uptime SLA |
| Turbopuffer query rate | $1/PB queried data | February 2026 reduction from $5/PB; 80% off 32-128 GB queried; 96% off >128 GB queried |
| Turbopuffer min billable per query | 1.28 GB | February 2026 increase from 256 MB |
| Turbopuffer namespace pinning | GB-hours billing | April 2026; minimum 64 GB and 10 minutes |
| Embedding compute (operator-side) | $0 (CPU/GPU electricity only) | Same regardless of search backend |

**Antiek's projected cost at single-operator scale** (~10k-100k
chunks, ~768-dim sentence-transformers vectors, ~50 queries/day):

- The **$64/month Launch tier floor** is the dominant cost.
- Per-query rate at 50 queries/day × 1.28 GB min-billable × 30 days
  = ~1,920 GB-queries/month. At $1/PB = ~$0.002/month — far below
  the $64 floor.
- Storage, writes: not on the public price page; calculator
  reference only. Assume they exist on top of the $64 floor.

**Total at operator scale: $64/month minimum, or $768/year.**

**The asymmetry — REVISED 2026-05-23**:

| Service | Operator-scale monthly cost (verified 2026-05-23) | Notes |
|---|---|---|
| `httpx` URL fetcher | $0 | In-process |
| DuckDB `cosine_similarity_sql` | $0 | In-process |
| Exa /search (within free tier) | $0 | 1,000 req/month free |
| Exa /search (above free tier) | $7/1k requests | March 2026 increase from $5/1k |
| Browserbase escalation (Wedge 2 volume) | $0 | 1 browser-hour/month free tier covers operator scale |
| **Turbopuffer Launch (operator scale)** | **$64/month minimum, regardless** | No free tier exists |
| Browserbase Developer | $20/month + overages | Antiek doesn't need this tier at Wedge-2 volume |
| Browserbase Startup | $99/month + overages | Comparable to Turbopuffer Scale tier |

**Turbopuffer's $64/month floor puts it in the same cost class as
Browserbase's paid plans.** Cost IS a constraint here, not just
quality. The Q1 draft of this spec assumed turbopuffer was
sub-dollar at operator scale ("cheaper than httpx" / "cost is
rarely the constraint"); the verified 2026-05-23 pricing
contradicts that. The spike (§6.4) must demonstrate quality
improvement worth $768/year against DuckDB cosine's $0/year — not
merely "≥10% improvement on ≥60% of queries."

### 11.2 Daily budget cap (default; configurable; revised 2026-05-23)

- `TURBOPUFFER_DAILY_BUDGET_USD`: $5. Note: the $64/month Launch
  tier floor dominates regardless of daily-budget enforcement —
  the cap is for runaway-cost protection on per-query spend, not
  the subscription floor. Even at $0 daily spend the operator
  pays $64/month.
- The combined acquisition-layer cap at
  `acquisition/search/__init__.assert_total_budget_ok` does NOT
  apply (turbopuffer is retrieval, not acquisition). Retrieval
  has its own per-service cap.
- Cap behavior: hybrid_search raises `TurbopufferBudgetExceeded`
  on the next call after threshold. Fallback to cosine is
  automatic — same loud-failure-then-degrade pattern as the
  outage path.
- **Subscription-floor accountability**: operator-facing monthly
  cost summary in `weekly_report.py` must surface the $64/month
  Launch floor as a fixed line item, not just per-query spend.

### 11.3 Legal envelope

- **Turbopuffer's TOS**: turbopuffer hosts BYO data. The customer
  is responsible for the legality of the data they index. Per
  Sprint 18's legal gate, banned-corpus content must NEVER reach
  turbopuffer (the gate enforces at ingestion, upstream of the
  sync layer). The sync layer additionally filters out chunks
  whose document is on the banned list, as a defense-in-depth.
- **AG MDL / Hachette / Bartz**: enforced at
  `substrate/legal_gate/` per the Exa spec; turbopuffer inherits
  the gate's refusals because the gate sits between DuckDB
  writes and turbopuffer sync.
- **GDPR / personal data**: turbopuffer hosts data physically;
  the operator becomes a joint data controller with turbopuffer's
  processor agreement (DPA). Sprint 22+ multi-user pivot must
  re-evaluate before exposing non-operator users to a turbopuffer-
  backed search.

### 11.4 Safety envelope

- **Turbopuffer cannot execute code**. It returns ranked rows.
  Safe.
- **Sync layer is fire-and-forget**. Turbopuffer outage degrades
  reads to cosine; does NOT block writes. The substrate stays
  available even when turbopuffer is down.
- **Stale-read window**. Reads against turbopuffer may return
  results that don't reflect the latest DuckDB state (sync lag).
  Bounded by the reconciliation pass cadence (default: hourly).
  For most operator queries this is invisible.
- **Embedding-model drift**. Re-encoding embeddings without
  re-indexing turbopuffer returns garbage results. Mitigated by:
  - The `embedding_meta` row recorded with each chunk's vector
    (model name + version + dimension) so a re-index pass can
    detect drift.
  - A manual operator-triggered `re-index` CLI subcommand that
    walks all DuckDB chunks and re-writes to turbopuffer with
    fresh embeddings.

---

## 12. Risks and mitigations

### 12.1 Stale-index drift

**Risk**: Sync from DuckDB to turbopuffer is eventually
consistent. A chunk written to DuckDB at t=0 may not be visible
in turbopuffer search until t=N. If the operator queries between
t=0 and t=N, they get incomplete results.

**Mitigation**:
- Sync layer fires the write within the same process tick as the
  DuckDB transaction commit. N is typically <5s.
- Reconciliation pass closes longer drift (default hourly).
- `HybridSearchDegraded` event documents fallback to cosine,
  which always sees the latest DuckDB state.
- Document the eventual-consistency property in the operator
  README so the operator doesn't expect read-your-writes
  semantics for turbopuffer hits.

### 12.2 Turbopuffer provider lock-in

**Risk**: Turbopuffer is a startup. SDK breakage, pricing changes,
or service incidents will happen. Migrating to a different vector
DB requires re-indexing every chunk.

**Mitigation**:
- Lazy SDK import in `substrate/graph/turbopuffer_index.py`. The
  module imports cleanly without the `turbopuffer` package
  installed; missing deps raise `TurbopufferUnavailable` (loud
  failure).
- Pin SDK version in `pyproject.toml` as an optional extra
  `turbopuffer = ["turbopuffer>=X.Y"]`.
- Cosine fallback means turbopuffer outages degrade rather than
  break.
- The chunk_id ↔ vector mapping is in DuckDB; switching to a
  different vector DB is "re-index every chunk through the new
  provider's write API" — non-trivial but bounded.

### 12.3 Embedding model migration

**Risk**: Operator migrates embedding models (sentence-transformers
→ a larger model). All existing turbopuffer vectors are stale.
Queries against the new model's vectors return garbage compared
against the old model's vectors.

**Mitigation**:
- Each chunk record carries `embedding_meta` (model name +
  version + dimension).
- The re-index pass detects model drift via mismatched
  `embedding_meta` and either:
  - Marks the namespace stale and degrades all queries to cosine
    until the re-index completes.
  - Triggers a background re-encode + re-write.
- Operator-explicit migration via CLI:
  `python -m substrate.graph.reconcile --re-encode-with new-model`.

### 12.4 Cost-as-DoS

**Risk**: A bug that loops on `hybrid_search` or `index_chunk` can
exhaust the turbopuffer budget in minutes.

**Mitigation**:
- Hard daily cap (`TURBOPUFFER_DAILY_BUDGET_USD`).
- Per-call cost logging into events.
- Weekly reporting via the existing `weekly_report.py` §7
  Acquisition cost section (extended with a turbopuffer sub-row).
- Same posture as Exa spec §6.7.

### 12.5 The cosine-fallback honeypot

**Risk**: The fallback-to-cosine path on turbopuffer outage is
silent (only the event log records it). The operator gets results
that look normal but are actually cosine — losing the BM25 +
filter dimensions that Wedge 1 was meant to provide.

**Mitigation**:
- `HybridSearchDegraded` event is emitted on every fallback.
  Weekly report surfaces "X% of queries this week were
  degraded."
- An operator-facing toast / log line on degradation is logged
  via the operator CLI on every degraded call (when running
  interactively).
- The fallback is OFF by default in spike mode (so the spike
  measures real turbopuffer, not silent cosine).

### 12.6 Legal-gate-bypass via turbopuffer cache

**Risk**: If turbopuffer holds a chunk whose document is later
added to the banned-corpus registry, the chunk could still be
returned by turbopuffer search before the next reconciliation
pass removes it.

**Mitigation**:
- The `hybrid_search` read path additionally consults the legal
  gate's `check_document` per result. A chunk whose
  source_document is on the banned list is filtered OUT before
  returning, even if turbopuffer holds it.
- Reconciliation pass removes legal-gate-banned chunks from
  turbopuffer at the next run.
- This is defense-in-depth: the gate at ingestion prevents
  banned content from being indexed; the read-time filter
  catches drift between ingestion-time and now.

### 12.7 Confidentiality at the provider boundary

**Risk**: Turbopuffer holds the operator's research substrate
chunks (text + embeddings + metadata). A turbopuffer breach
would leak the operator's research data to whoever accesses the
breach.

**Mitigation**:
- Turbopuffer's SOC 2 attestation + DPA are reviewed before any
  production data lands.
- Chunks stored in turbopuffer are the same text already
  potentially exposed via Exa indexing — most operator research
  is over already-public sources. Sensitive operator-private
  documents (interview transcripts, private notes) get a
  `do_not_index_in_turbopuffer=True` flag on their substrate row,
  and the sync layer respects it.
- The chunk_text in turbopuffer is identical to what's in DuckDB.
  The substrate is the source of truth; turbopuffer adds no new
  attack surface vs. a DuckDB backup leak.

---

## 13. Unlock criteria for promoting wedges

Each wedge has explicit gates. Crossing them is the ratification
event.

### 13.1 Wedge 1 (Hybrid search) unlock criteria — tightened 2026-05-23

The spike (§6.4) is the single load-bearing gate. **The 2026-05-23
pricing-verification pass tightened the win-threshold to reflect
the $64/month Turbopuffer Launch floor** ($768/year cost-of-entry
against DuckDB cosine's $0/year). The prior "≥10% on ≥60%" bar
assumed turbopuffer was sub-dollar at operator scale; that
assumption is now known to be wrong (§1.3, §11.1).

- [ ] Operator-hand-curated 20 queries representing real research
      questions.
- [ ] Operator graded the current `cosine_similarity_sql` top-10
      on each query (0-3 scale, sum per query).
- [ ] Turbopuffer hybrid run against the same 20 queries.
- [ ] **Hybrid scored ≥15% higher than cosine on ≥70% of queries**
      (was ≥10% on ≥60%; tightened 2026-05-23 to justify the
      $64/month subscription floor against $0/year DuckDB
      cosine).
- [ ] Operator has read this section's cost framing in §11.1 and
      affirmatively decided the spike-projected quality gain is
      worth $768/year.

If all five close: Wedge 1 ships per §6.5.
If hybrid loses on ≥50% of queries OR if the operator declines the
cost commitment in the fifth criterion: Wedge 1 moves to permanent
REJECT, documented in §10 with the date and a link to the spike
data + the cost-commitment decision.
If between (inconclusive on quality bar): expand to 50 queries and
re-run, OR DEFER.

### 13.2 Wedge 2 (Discovery-event search) unlock criteria

- [ ] Wedge 1 ratified.
- [ ] Sprint 19 discovery-review UI surface has shipped per
      Exa & Browserbase spec §14.1.
- [ ] Operator has used the discovery review for ≥30 days and
      can articulate which queries the BM25 + filter shape would
      improve (the analogue of §6.4's spike data for discoveries).
- [ ] Retention pass (§14.1 Exa spec) interplay verified — Wedge
      2 indexes only the live 30-day window; rolled-up summaries
      stay in `discovery_summary` only.

### 13.3 Wedge 3 (Shared public graph search) unlock criteria

- [ ] Multi-user pivot shipped (Sprint 22+; per master-spec §13.4).
- [ ] DuckLake catalog operational (master-spec §13.2 architecture 2).
- [ ] Cross-user query patterns documented from ≥30 days of multi-
      user operation. The operator can articulate which queries
      span users (i.e., why a per-user-DuckDB-only search isn't
      sufficient).
- [ ] DPA (Data Processing Agreement) with turbopuffer reviewed
      for the multi-user case.

### 13.4 Wedge 4 (Federation substrate) unlock criteria

All of these. Stringent on purpose.

- [ ] Federation design landed in master-spec or a dedicated spec
      (consent model, citation flow, trust boundaries, sybil
      resistance).
- [ ] ≥3 federated instances actually exist + want to share
      embeddings.
- [ ] Wedges 1, 2, 3 all shipped and operated for ≥60 days.
- [ ] Cross-instance per-query cost cap pattern defined and
      operator-reviewed.
- [ ] Comparison against non-turbopuffer alternatives (a shared
      DuckLake catalog with replication; a custom vector
      federation layer; etc.) documented — turbopuffer must
      win on at least one principled axis (cost, latency,
      operational simplicity, consent enforcement) over the
      alternatives.

If any criterion fails to ratify, the verdict moves from DEFER to
REJECT permanently.

---

## 14. Sprint placement

| Sprint | Theme | Turbopuffer work |
|---|---|---|
| **17** | Interview voice mode + integration spec items | **None.** This spec exists as future scaffolding; no code work this sprint. |
| **18** | Retrieval-time legal gate + publisher dashboard | **Spike (§6.4) lands here** if the operator wants Wedge 1 in Sprint 19. ~1 day of operator+assistant time. |
| **19** | Notebook surface + Exa & Browserbase Wedges 1 + 2 | **Wedge 1 main work** if spike ratified. ~3 days of focused work. |
| **20** | Trajectory replay + Wedge 3 corroboration | Wedge 1 ratifies. **Wedge 2 begins** once Sprint 19 discovery-review UI lands. |
| **21-22** | Synquery + Phase 8 enforcing + multi-user prep | Wedge 2 ratifies. Wedge 3 design begins (no code). |
| **22+** | Multi-user pivot + two-graph architecture | **Wedge 3 ships** alongside the multi-user pivot, if its unlock criteria close. |
| **25+** | Federation / network effects | **Wedge 4 re-evaluation.** Possibly REJECT permanently if Wedges 1-3 cover the actual query needs. |

**Critical sequencing constraints:**
- Wedge 1 cannot ship before the spike (§6.4).
- Wedge 2 cannot ship before Wedge 1 ratifies + Sprint 19 discovery-
  review UI lands.
- Wedge 3 cannot ship before the multi-user pivot (Sprint 22+).
- Wedge 4 cannot ship before federation design lands.

**What's NOT on the critical path:**
- The schema additions in §6.3 can land as a substrate-only PR
  ahead of any wedge (precursor pattern, same as Exa spec §18.3).

---

## 15. Open questions (genuinely unresolved)

These are the questions this spec does NOT settle. Each requires
operator decision before the wedge it gates lands.

### 15.1 Does the spike use the existing sentence-transformers embeddings, or fresh embeddings?

The substrate's existing embeddings are sentence-transformers
default model (`all-MiniLM-L6-v2` or whatever's currently wired
in `processing/embedding/embed.py`). Re-encoding for the spike
adds a day of compute on 1k chunks but eliminates "the embedding
model is wrong" as a confounding variable in the spike
comparison.

**Recommendation**: re-encode for the spike with the operator's
chosen production model. The comparison must be apples-to-apples;
turbopuffer hybrid against sentence-transformers vectors that
were optimized for a different vector DB introduces noise.

**Operator decision needed before the spike runs.**

### 15.2 Per-investigation namespace vs single shared namespace?

The spec recommends one shared `substrate.chunks` namespace for
Wedge 1. Per-investigation namespaces (`investigations.{inv_id}.chunks`)
add isolation but fragment the warm cache and add ops complexity.

**Recommendation**: single shared namespace until query volume
exposes specific isolation needs.

**Operator decision needed only if Wedge 1 multi-investigation
queries hit cache locality problems.**

### 15.3 What's the right alpha (BM25/vector blend)?

Spec §6.1 leaves `alpha` operator-controllable per-query, default
0.5. Operator may want different defaults for different query
classes (more keyword-heavy for technical queries; more vector-
heavy for descriptive queries).

**Recommendation**: 0.5 default; per-query override; document the
heuristic.

**Operator decision needed during Wedge 1 implementation.**

### 15.4 Do we add a `do_not_index_in_turbopuffer` flag to the documents table?

The spec at §12.7 mentions this for confidentiality-sensitive
documents (interview transcripts, private notes). Adding the
flag is a schema change.

**Recommendation**: add the flag as part of Wedge 1's schema
work. Operator can flip it per-document at ingestion time;
default OFF (everything indexed) for backward compat.

**Operator decision needed before Wedge 1 ships.**

### 15.5 Reconciliation cadence

Spec §6.6 mentions reconciliation runs hourly by default. Operator
may want more frequent (every 10 minutes — costs more turbopuffer
queries to detect drift) or less frequent (daily — drift window
widens).

**Recommendation**: hourly default; operator-configurable via env
var `ANTIEK_TURBOPUFFER_RECONCILE_INTERVAL_HOURS`.

**Operator decision optional; default works.**

### 15.6 Does Wedge 2's discovery-event search need its own embedding model?

Discovery events have a different shape than substrate chunks
(URL + title + snippet, not full chunked text). The substrate's
chunk embeddings might not be the right shape for URL-shaped
queries.

**Recommendation**: defer the question until Wedge 2 actually
starts. Likely answer: reuse sentence-transformers for
consistency; revisit if Wedge 2 quality is poor.

**Operator decision needed if Wedge 2 ships.**

### 15.7 Does the spike count toward the §6.4 unlock?

The spike runs against ~1k chunks for cost/time reasons. The
production Wedge 1 sync indexes the full substrate. If the spike
wins at 1k chunks but production at 100k chunks shows different
quality dynamics, is the unlock decision re-opened?

**Recommendation**: the spike is the gate for SHIPPING Wedge 1.
After ship, a separate "production validation" pass measures
hybrid vs cosine on the full substrate. If production validation
shows hybrid losing on ≥50% of queries, Wedge 1 is rolled back
(feature flag off; cosine becomes default).

**Operator decision needed before the spike to set the rollback
threshold.**

---

## 16. What to do now

**Zero INTEGRATE-NOW items.** Every wedge below INTEGRATE has a
sequencing constraint (Wedge 1: spike; Wedge 2: Wedge 1 + UI;
Wedge 3: multi-user pivot; Wedge 4: federation design).

### 16.1 The spike (§6.4) is the operational next step

If the operator wants any turbopuffer wedge in Sprint 18-19:

1. Operator sets `TURBOPUFFER_API_KEY` (free tier sufficient).
2. Operator hand-curates 20 queries representing real research
   shapes they've asked or wished they could.
3. Operator grades the existing `cosine_similarity_sql` top-10
   per query.
4. Spike harness indexes ~1k random sample of chunks into a
   throw-away turbopuffer namespace.
5. Spike runs each query through hybrid.
6. Operator grades hybrid's top-10 the same way.
7. Verdict per §13.1 unlock criteria.

Total operator time: ~3 hours (mostly the grading).
Total assistant time: ~1 day (spike harness + analysis).

### 16.2 If the spike wins

Wedge 1 ships per §6.5 (~3 days). Wedge 2 sequences behind it
gated on Sprint 19 discovery-review UI. Wedge 3 stays DEFER until
Sprint 22+. Wedge 4 stays DEFER possibly REJECT.

### 16.3 If the spike loses

This spec's verdicts update:
- Wedge 1 moves to REJECT permanently with the dated spike data.
- Wedge 2 moves from PHASE 2 to DEFER (it inherits Wedge 1's
  sync layer; without Wedge 1 there's no sync layer).
- Wedge 3 stays DEFER (Sprint 22+ may justify it on multi-user
  scale grounds even if single-operator scale doesn't).
- Wedge 4 stays DEFER.

### 16.4 If the operator never runs the spike

This spec sits in the docs as future scaffolding. The verdicts
remain unratified; no code ships. That's a defensible state —
turbopuffer is a Sprint 18+ option, not a Sprint 17 obligation.

### 16.5 The twelve explicit REJECTs

§10.1-10.12 close the bait that "turbopuffer is better
infrastructure" implies — turbopuffer-as-primary, turbopuffer-as-
dispatch, per-user-private replacement, synchronous sync,
wholesale cosine kill, discovery layer, embedding host, embed-
model migration without re-index, legal-gate enforcement point,
per-user before multi-user, custom scoring, graph traversal.
These are not deferred; they are settled negative.

### 16.6 The principle restated

**Turbopuffer is a secondary read-optimized index over substrate-
owned data. DuckDB stays primary. The arrow is unidirectional.
The fallback is always cosine. The substrate-as-source-of-truth
invariant holds.**

Turbopuffer makes the retrieval layer smarter on the dimensions
DuckDB cosine misses (BM25 keyword grounding, native filters).
That's the value proposition. It's also the only value
proposition — *every other framing in §10 is REJECT*.

The integration is the wedges in §6-§9. The rejections in §10
are the guardrails. The spike (§6.4) is the gate. The unlock
criteria in §13 are the ratchet. The verdict on Wedge 1 (the
only INTEGRATE-CANDIDATE) lands the same day the spike runs,
not earlier.

---

## Final note for the implementing agent

When this spec conflicts with another, precedence is:

1. `architecture_notes.md` — substrate invariants (never violate).
2. `master-product-spec.md` — product vision + sprint sequencing.
3. `strategy/voice-and-style-discipline.md` — synthesis quality bar.
4. `integration_exa_browserbase.md` — peer integration; same
   wedge-style discipline applies here.
5. This spec — turbopuffer integration verdicts and wedge
   mechanics.
6. Other peer integration specs — conflicts resolved by operator
   review.

If precedence (1) and any wedge ever conflict — i.e., adopting a
turbopuffer pattern would weaken the substrate-as-source-of-truth
invariant — the substrate wins. The wedges in §6-§9 are the
means; the substrate is the end. **Never substitute the end for
the means.**

The retrieval layer is what turbopuffer addresses. The substrate
write layer is not its concern. The discovery and ingestion
layers belong to other primitives (Exa, Browserbase,
`acquisition/urls/`). Borrow ruthlessly from turbopuffer where
the retrieval-shape primitive fits. Reject loudly where it
doesn't. Use the spike unlock as the ratchet — and re-evaluate
the rejections (§10) only when the underlying substrate state
changes meaningfully, not because turbopuffer ships a new feature
or the headline trends shift.
