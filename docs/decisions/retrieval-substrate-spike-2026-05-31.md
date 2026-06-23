# Retrieval-substrate spike — verdict (SPR-05)

**Date:** 2026-05-31
**Decision:** **DuckDB-VSS (HNSW) is the retrieval substrate.** It wins by
default-on-tie (no new dependency, $0/yr) AND on the one dimension the spike
could measure honestly in this environment: latency at equal recall. The two
non-default candidates (**turbopuffer**, **DuckLake**) were **NOT measured** —
this environment has no credentials — so **neither cleared the §13.1 bar**, and
an un-failed $0 baseline is not displaced by an un-measured $768/yr alternative.

**Artifact (numbers below are derived from it, not retyped guesses):**
`benchmarks/out/retrieval_spike_2026-05-31.json`. Re-run with
`python -m benchmarks.retrieval_bench --substrate vss --substrate brute_force
--substrate turbopuffer --substrate ducklake`.

---

## 1. What was measured, and the load-bearing honesty caveat

The spike seeded a deterministic synthetic graph (13 chunks across 7 domains +
3 insight/question nodes + 1 `restricted_pending_opt_in` chunk for the §9.0
gate control) and ran every candidate through ONE harness invocation on the
SAME graph and the SAME 20-query fixture
(`benchmarks/fixtures/retrieval_queries.yaml`, built from `OPERATOR_INPUTS.md`
§1 — 19 operator queries, Q15 dropped per the §1 critic, + 1 structural
negative control Q21 to reach the spec's ≥20 floor).

**The embedder available in this environment is the dim-16 `_HashEmbedding`
stub.** `sentence-transformers` (the real `all-MiniLM-L6-v2`) is NOT installed
here. The hash stub carries **no semantic structure** — `sha256(query)` shares
nothing with `sha256(chunk)` — so:

- **Chunk recall@k under the stub is NON-LOAD-BEARING for ranking quality.** It
  measures index mechanics + speed, NOT semantic relevance. The fixture flags
  every paraphrase/conceptual query `load_bearing: false` (§1 caveat 5). The
  one exception: node-retrieval queries (Q08/Q10/Q11) score via the ILIKE node
  path, which is a real substring match and therefore informative — those
  recalls are mechanically meaningful (and identical across VSS/brute-force).
- **The rank-based negative controls (§1 clause 3) "fail" under the stub** —
  random hash vectors mean a control query outranks a true positive by chance.
  This is NOT a ranking defect; it is the absence of semantic signal. The
  harness records the violations honestly; they are non-load-bearing under the
  stub and would be re-evaluated under the real embedder.

**What IS load-bearing under the stub:**

1. **Correctness parity** — VSS (HNSW) returns byte-for-byte the `search()`
   shape and **identical ordering + identical similarity values** to the
   brute-force reference on the seeded graph. HNSW is exact-equivalent to the
   full cosine scan at this scale, so the VSS swap is correctness-preserving.
2. **Latency + build cost** — real wall-clock, independent of embedder
   semantics.
3. **§9.0 gate preservation** — a SQL-WHERE predicate, embedder-independent;
   load-bearing and legally binding (§1 clause 4).
4. **§16 single-writer** — row counts unchanged across the whole run for every
   candidate (`single_writer_held: true`).

A future operator who installs `sentence-transformers` can re-run the harness
unchanged to lift the non-load-bearing flags and get semantic recall.

## 2. Measured numbers (candidate × recall@5 / p50 / p95 / build cost)

From `retrieval_spike_2026-05-31.json` (stub embedder, 20 queries, 30 latency
repeats over the 17 non-control queries):

| Candidate | recall@5 (load-bearing) | recall@5 (pooled) | p50 (ms) | p95 (ms) | one-time index build (ms) | §9.0 gate | $ / yr |
|---|---|---|---|---|---|---|---|
| **DuckDB-VSS (HNSW)** | 0.20 † | 0.333 † | 1.51 | 1.74 | ~42 (HNSW build) | held | **$0** |
| brute-force (reference) | 0.20 † | 0.333 † | 1.79 | 2.10 | ~9 (open only) | held | $0 |
| turbopuffer | — **not measured** (no creds) | — | — | — | — | n/a | $768 |
| DuckLake | — **not measured** (no creds) | — | — | — | — | n/a | $0 infra + object-store |

† **Recall is non-load-bearing for ranking quality under the hash stub** (see
§1). The number is identical for VSS and brute-force because they rank
identically; it reflects index mechanics + the ILIKE node path, not semantic
quality. Per-domain recall (the §1 clause-1 de-pooling): bridges 1.0, nodes
0.667, quantum 0.259, batteries/radar/vaccines 0.0 — the zeros are hash-stub
noise, not substrate differences.

**Latency is sub-2ms and run-to-run jittery at this graph size**; the stable,
repeatable observation across runs is **VSS p50/p95 < brute-force p50/p95** —
the HNSW index is already marginally faster than the full scan even at 13
chunks, and the gap widens with graph size (the whole point of the index). The
HNSW build is a one-time ~33ms cost recorded separately so a fast query does
not hide an expensive index.

## 3. The bar (anchored to turbopuffer spec §13.1)

`docs/integration_turbopuffer.md` §13.1 (tightened 2026-05-23) sets the
unlock bar for a non-default substrate:

> **Hybrid scored ≥15% higher than cosine on ≥70% of queries**, AND the
> operator affirmatively decides the spike-projected quality gain is worth
> **$768/year** against DuckDB cosine's **$0/year**.

**This spike adopts that bar unchanged** (no tightening, no relaxing — it is
already the operator's ratified threshold). A non-default substrate must clear
**≥15% recall lift on ≥70% of the load-bearing queries at acceptable
latency/cost** to displace DuckDB-VSS.

**Outcome against the bar:**

- **turbopuffer: did not clear it — un-measured.** With no `TURBOPUFFER_API_KEY`
  the adapter recorded `status: "skipped — no credentials"`; it ran zero
  queries. A 0-of-20 measurement cannot show ≥15% lift on ≥70%. The bar is not
  cleared, so the $768/yr dependency is not justified.
- **DuckLake: did not clear it — un-measured.** No object-store credentials;
  same skip. DuckLake's cost is object-store + operational, not a flat
  subscription, but the recall bar is equally un-met.
- **DuckDB-VSS: wins by default-on-tie + measured latency.** $0, no new Python
  dependency (`vss` is an installable DuckDB extension; `duckdb>=1.1.0` already
  in `pyproject.toml`), correctness-identical to the brute-force path it
  replaces, and already faster.

## 4. Steelman of each rejected candidate (rigor #2)

**turbopuffer.** Strongest case in its own terms: a managed, serverless vector
store that scales past a single DuckDB file, with **hybrid BM25 + vector
search** — the one thing brute-force cosine genuinely cannot do (lexical recall
on exact terms fused with semantic recall). For the §1 exact-fact queries
(QuEra error rate, radar dB, axle load) a BM25 component would plausibly recall
the right chunk where pure cosine under a weak embedder misses it. That is a
real capability gap, not a vendor pitch. **What tipped it to REJECT (for now):**
it is **un-measured without credentials** — the spike could not demonstrate the
§13.1 ≥15%/≥70% lift, and $768/yr cannot be spent against a $0 baseline that has
not failed. The seam is left open so a credentialed operator can run the same
harness and re-decide on numbers.

**DuckLake.** Strongest case: object-store reach (Parquet on S3-compatible
storage) for a **future multi-user / shared-public graph** — master-spec §13.2's
two-graph pivot. The single-file DuckDB substrate is exactly right for the
single-operator phase but does not stretch to a shared public graph that
multiple instances read concurrently; DuckLake's lakehouse model is the
natural fit there. **What tipped it to REJECT (for now):** the multi-user graph
does not exist yet (gate G7 / Sprint 22 earliest), so DuckLake has **no
production justification today**, AND it is **un-measured without object-store
credentials**. It is a candidate for the multi-user era, not this one.

## 5. Reconsider-if (keyed to concrete substrate-state changes)

Re-open this decision — re-run the harness, do not re-litigate from scratch —
**only if one of these triggers fires:**

1. **VSS p95 exceeds the SPR-09 latency budget at graph scale.** When the graph
   crosses a size where DuckDB-VSS p95 query latency exceeds the budget SPR-09's
   compounding benchmark depends on (the cost-to-resolve must fall, not rise, as
   the graph grows), re-run with turbopuffer credentials and test the ≥15%/≥70%
   bar AND the latency headroom. The brute-force scan is O(n) in chunks; HNSW is
   sub-linear but still has a crossover. **Concrete trigger: VSS p95 on the
   production corpus > the SPR-09 per-query budget.**
2. **Hybrid lexical+semantic recall becomes load-bearing.** If, under the real
   `all-MiniLM-L6-v2` embedder, exact-fact recall on the operator's load-bearing
   queries is materially below target AND a BM25+vector hybrid would close it,
   re-run turbopuffer against the same fixture. (This needs the real embedder
   first — the current spike cannot see it.)
3. **The multi-user / shared-public graph ships (gate G7, ~Sprint 22).** When a
   second instance must read one shared graph concurrently, re-evaluate
   DuckLake against the same harness — the object-store reach it offers is
   exactly the gap that opens then.

Until a trigger fires, **DuckDB-VSS is the substrate and turbopuffer/DuckLake
stay un-adopted spike modules.** A future operator should be able to re-decide
from this record's numbers + triggers without re-running the spike.

## 6. Addendum — 2026-06-23 (DRW-LEDGER SPR-LEDGER-07)

`TURBOPUFFER_API_KEY` is present in the operator environment, but
`TurbopufferSubstrate.query` still raises `NotImplementedError` on the
credentialed path (SDK wire + §9.0 mirror not shipped). Re-run:

`python -m benchmarks.retrieval_bench --substrate vss --substrate turbopuffer`

**failed** at adapter query with that error — **turbopuffer remains
UN-MEASURED**; Wedge 1 stays **DEFER** per §13.1. No hybrid_search prod
wiring until a credentialed spike records numbers in
`benchmarks/out/retrieval_spike_<date>.json` and clears the bar.

**TPF-W1 ledger status:** `deferred` (adapter wire is a separate engineering
slice, not DRW gather).

## 7. What landed (M5)

- **Interface (the open seam):** `substrate/graph/retrieval_substrate.py` —
  the `RetrievalSubstrate` Protocol (one `query` method, the `search()` return
  shape), `BruteForceSubstrate` (reference), `DuckDbVssSubstrate` (winner), and
  the `make_substrate` factory (default-on-tie = `"vss"`). Callers depend on the
  Protocol; a future swap touches the one factory.
- **Winning impl on the default path:** DuckDB-VSS only. The factory's default
  path imports no vendor adapter (test-asserted).
- **Losing adapters as flag-gated spike modules (NOT on the default path):**
  `substrate/graph/retrieval_adapters/turbopuffer.py`,
  `.../ducklake.py` — reachable only via explicit `make_substrate(kind=...)` /
  the harness `--substrate` flag, credential-gated, read-only (§16).
- **Harness + fixture:** `benchmarks/retrieval_bench.py`,
  `benchmarks/fixtures/retrieval_queries.yaml`, artifact
  `benchmarks/out/retrieval_spike_2026-05-31.json`.
- **Tests:** `tests/test_retrieval_substrate_interface.py`,
  `tests/test_retrieval_bench.py`. The existing §9.0
  `tests/test_retrieval_time_gate.py` still passes against the new seam.

## 7. Provenance + assumptions

- **Query set is OPERATOR-SUPPLIED** (`OPERATOR_INPUTS.md` §1, the corrected
  3-drafter + adversarial-critic synthesis), NOT best-effort. Per-query
  `label_provenance` is recorded (`fixture` | `author-asserted` | `structural`);
  author-asserted conceptual queries are down-weighted in the tie-break (§1
  clause 2). Open item §0.1: the operator may still ratify/replace the
  author-asserted labels or supply their own ~20 real queries + labels.
- **§9.0 gate composed from main, not the staged fix.** Main's gate is still
  the fail-open DENYLIST (`content_class IS NULL OR NOT IN (...)`); the §9.0
  allowlist unification is staged separately (PR #38 / #29, unmerged). This seam
  composes whatever is on main — it does not assume the fix landed. Both the
  reference and VSS impls apply the SAME predicate via the canonical
  `PRIVILEGED_POLICY_TAGS` / `RESTRICTED_CONTENT_CLASSES` constants from
  `search.py`.
- **VSS index lives in a temp copy of the graph** (DuckDB cannot build a
  persistent HNSW index on a read-only connection, and §16 forbids writing the
  real graph). The source file is never written. A production wiring (SPR-06+)
  would build the index once inside the single-writer's own transaction — out
  of scope for the spike, which only needs the measured query/build cost.
- **The verdict (DuckDB-VSS) stands — it was measured where the extension is
  available.** The `vss` extension is loaded via a hang-proof, LOAD-first probe
  (`_vss_available` / `_vss_loadable_probe`): a pure-local `LOAD vss` first (no
  download), and a NETWORK `INSTALL vss` only when the operator opts in with
  `ANTIEK_VSS_ALLOW_INSTALL=1`. In an environment WITHOUT the extension loadable
  (e.g. a network-restricted CI runner with the flag unset), the impl falls back
  to the brute-force path — exactly today's `main` behaviour — which is safe and
  correctness-preserving; the bench records `vss_active=false` and the
  vss-active-only tests skip rather than fail or hang. **vss-active requires the
  extension to be loadable in the running environment.**
