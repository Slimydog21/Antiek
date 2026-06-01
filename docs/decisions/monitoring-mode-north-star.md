# Monitoring mode — the thin slice, and the deferred north star

**Sprint:** SPR-09 (Personal-Reading Lane & Ambient Ingest, Wave 4)
**Status:** thin slice shipped; full ambient-research product deliberately deferred
**Code:** `orchestration/monitoring/` (the module docstring links back here)

This note is the defensibility artifact for monitoring mode. It records
*what was built*, *what was deliberately left out*, and *the named
condition under which the deferral reverses*. A future maintainer should
be able to reconstruct from this file alone why monitoring mode is a thin
slice and what the next spec would own.

## What the thin slice IS

The brief seeded an ambient-research product inside the X ask — *"a
continuous feed on ongoing new ideas… an ambient mode of research that
functions like Bezos's 'puttering' where one can frolic in information."*
SPR-09 ships exactly four things, and no more:

1. **One MONITOR object** — a saved feed bound to **one** prior
   deep-research investigation. It stores the thread's salient query
   terms, an embedding centroid (the mean of the thread's chunk
   embeddings), and a `last_seen_at` checkpoint. Persisted in the
   `monitors` table inside `ANTIEK_GRAPH_SCHEMA_V1_SQL` — never a
   side-file store.
2. **A resumable REFRESH** — surfaces the `personal_reading` documents
   ingested since the checkpoint, ranks them against the centroid,
   advances the checkpoint, and returns the new items **exactly once**.
3. **A "puttering" read surface** — a grazing feed (relevance- or
   chronologically-ordered, **not** a query box) with full bodies on the
   owner path only, every item proven non-attributable.
4. **This note.**

## What the full product (the NORTH STAR) would add — and why each is deferred

| Deferred capability | Why deferred |
|---|---|
| **A learned relevance-ranking model** (recency-decay tuning, interaction-boost scoring) | Ranking here is cosine-against-centroid or chronological fallback only. A learned ranker is its own substrate (training data, eval, an export the personal lane is *excluded* from) — it cannot be a side-effect of a thin slice. |
| **Multi-thread / multi-monitor fan-in** | One monitor over one investigation keeps the data model and the lane-isolation proof simple. Cross-monitor aggregation changes the ranking surface and the checkpoint semantics; it earns its own design. |
| **Serendipity / off-thread "surprise" injection** | The whole *point* of "frolic in information" — but it deliberately surfaces OFF-thread content, which is a different relevance contract and a different lane-isolation argument. Not a refinement of the on-thread feed; a new feature. |
| **Any always-on / self-updating scheduling** | See the §16 box-bounded reason below. This is the single most-tempting expansion and the one most explicitly deferred. |

## The §16 box-bounded constraint (why no daemon ships here)

Refresh is **operator-invoked** (`python -m orchestration.monitoring
--refresh <monitor_id> --once`) or reuses the existing
`orchestration/continuous` single-iteration pattern. It adds **no**
`.service`/`.timer`, **no** thread, **no** long-lived process.

The tempting alternative — drive refresh off the existing
`antiek-continuous-research.service` systemd timer so the feed updates
itself — is genuinely nicer UX (the operator never clicks "refresh"). But
an always-on refresh is **a second long-lived writer against the §16
single-writer DuckDB box**, and a new daemon the master spec's
Open-Questions explicitly defers. The binding precedent is the operator
decision recorded in the master spec ("refresh stays operator-invoked +
reuses the continuous-research pattern"). The single-writer invariant
(`runtime/db_lock.connect_write`, `--workers 1`) is non-negotiable; every
monitor write in `orchestration/monitoring/monitor.py` funnels through it.

## The reversal condition (the deferral is reversible, not forgotten)

The full ambient-research product earns its **own spec** only after the
thin slice **gets real daily use and the operator validates the puttering
loop** (the master-spec key-design-decision trigger). Until then, the
deferrals above stand. This is a named, checkable condition — not a
permanent rejection.

## Lane invariants this slice preserves (for the SPR-10 audit)

- The feed surfaces `content_class='personal_reading'` **only** (lane
  isolation; filtered in the query AND re-checked in `putter_feed`).
- Every item is proven non-attributable via
  `substrate.collective_graph.eligibility.is_attribution_eligible`
  (`personal_reading` ∈ `NON_ATTRIBUTABLE_CONTENT_CLASSES`).
- Full bodies are returned only on the owner / `operator_only` path; the
  public `attribution_eligible` gate never sees the body
  (`substrate.graph.search` excludes `personal_reading`).
- No money path is touched: `personal_reading` accrues zero ad
  attribution and zero IP escrow by construction.
