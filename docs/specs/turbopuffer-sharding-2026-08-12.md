# Turbopuffer Namespace Sharding — Integration Addendum (2026-08-12)

**Status**: operator-brief response ("build with Turbopuffer and embed their new
sharding feature"). Companion to `docs/integration_turbopuffer.md` (spike-first
verdict matrix). All sharding facts verified against turbopuffer.com/docs/sharding
on 2026-08-12.

---

## 1. What Namespace Sharding is (verified)

- Default: a namespace = one index. Sharding transparently partitions a
  namespace's documents across N internal shards by `hash(id) % num_shards`.
- **No client-side fan-out, no new API**: clients keep talking to one namespace;
  the engine fans writes and queries to shards and merges results.
- One shared write-ahead log per namespace; a write commits once with
  all-or-nothing semantics; reads see it immediately.
- **Strongly consistent queries are preserved** (each shard reads the same
  namespace snapshot). Eventually-consistent queries are weaker per shard.
- `num_shards` is set **on the namespace's first write** and **cannot be
  changed in place** — resize by copying into a new namespace.
- Sizing: ≤1 TB per shard, ≤500M docs per shard, ≤256 shards, 256 TB max
  namespace. Rule of thumb: `num_shards ≈ ceil(expected_size / 1 TB)`, rounded
  up for headroom; avoid over-sharding (query tail latency; volume-discount
  delay on query pricing).
- Pricing: unchanged; no per-shard fee; each sub-query bills its shard size.

## 2. Why this matters for Antiek

Antiek's substrate today is DuckDB (~950 MB); the Turbopuffer wedges
(integration_turbopuffer.md) are spike-first and deferred behind unlock
criteria. Sharding is therefore **not an immediate need** — it is a
**first-write configuration decision** that cannot be retrofitted cheaply
(copy-to-new-namespace is the only resize path).

## 3. Decision

**Adopt `num_shards` from day one of Wedge 1 (hybrid search spike), sized for
the 3–5 year trajectory, not today's corpus.** Rationale:

- The cost of setting it early is ~zero (pricing is unchanged; a small
  namespace across 2 shards behaves identically to the operator's calls).
- The cost of NOT setting it is a copy-to-new-namespace migration later,
  exactly the retrofit the master spec's §13.6 discipline warns about.
- Sizing: Antiek's full corpus (documents+chunks+notes at 100M+ chunks in 5
  years) fits one shard today and 2–4 shards long-term. Recommend
  `num_shards = 2` at wedge-1 first write (rule of thumb: ceil(100GB/1TB)=1,
  round up for headroom → 2), with the sharding plan documented so a future
  resize is a deliberate, spec'd migration.

## 4. Integration points (concrete)

1. `substrate/graph/retrieval_adapters/turbopuffer.py` — the SPIKE adapter
   must set `sharding: {num_shards: 2}` in namespace metadata on first write
   (namespace metadata API), and log the chosen config into the substrate's
   typed event log (`turbopuffer_namespace_configured` event) so the choice is
   auditable.
2. `substrate/graph/retrieval_substrate.py` — the adapter factory already
   switches on `kind == "turbopuffer"`; add `shard_count` to `adapter_kwargs`
   with default 2 and a REJECT guard against >256 and against changing it on an
   existing namespace (fail loudly, never silently re-create).
3. Spike gates (from integration_turbopuffer.md §13): Wedge 1 still requires
   ≥15% on ≥70% win vs DuckDB cosine before promotion; sharding config ships
   with the spike harness so the measurement is on the sharded namespace.
4. Cost note: a query on a sharded namespace bills per shard size — with 2
   shards the billed size sum equals the namespace size (no change); document
   in the wedge-1 cost ledger.

## 5. Guardrails

- Never over-shard: tail latency = slowest shard; volume discounts scale with
  namespace size. 2 shards until data is >100 GB.
- Strong-consistency requirement for the substrate (claim→chunk→document
  retrieval must not see partial snapshots) is preserved by sharding — the
  adapter must request strongly-consistent reads (default) and never the
  eventually-consistent mode.
- Resize = copy to new namespace with new `num_shards`, then cut over and
  delete old — a spec'd migration with backup, never an in-place mutation.

## 6. Open items

- Confirm Turbopuffer's namespace-metadata write path in the TS/SDK (adapter
  spike will verify; the openapi spec is in github.com/turbopuffer/turbopuffer-openapi).
- Decide wedge-1 timing (deferred until the operator's corpus shows a real
  retrieval failure — per integration spec §13).
