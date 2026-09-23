# Turbopuffer sharding — DEFER stands; the 2026-08-12 adoption directive is superseded

**Date:** 2026-09-20 (written 2026-09-22 against `origin/main` 27291eb59)
**Source spec:** `~/specs/antiek-v1-connect/SPR-09-infra-scale.md`, task 1
**Status:** DEFER. `num_shards` is set on no Antiek namespace, and this document is
the reason it stays that way until one of the numeric triggers below fires.
**Supersedes:** `docs/specs/turbopuffer-sharding-2026-08-12.md` §3 ("Adopt
`num_shards` from day one of Wedge 1 ... Recommend `num_shards = 2`") and its §4.1
and §4.2 integration directives. That file now carries a SUPERSEDED banner
pointing here. Its §1 (what sharding is, verified against the vendor docs) and
§5 guardrails are still accurate and are not superseded.
**Agrees with:** `docs/anti-ek-vision-map-2026-09-17.md`, whose Pillar 4 table
(line 118) and roll-up (line 217) both mark the 08-12 plan **DEFER** "until
servable corpus proves need".

## The contradiction this closes

Two documents were live on main with opposite verdicts. The 08-12 addendum said
adopt sharding at the first write of Wedge 1 and gave concrete integration
instructions (set `sharding: {num_shards: 2}` in namespace metadata; add
`shard_count` to `adapter_kwargs`). The 09-17 vision map said defer. Wedge 1 then
shipped — 4,837 rows servable, no sharding — so the 08-12 directives became stale
instructions sitting on main, waiting for an agent to execute them against a
namespace that already exists. Executing them would not even be wrong so much as
pointless (fact 1) and, done in place, impossible (the SDK fixes sharding at a
namespace's inaugural write). This document makes DEFER the single verdict.

## Decision

DEFER. Do not set `sharding: {num_shards: N}` on any namespace. Do not add
`shard_count` to the adapter factory. Do not carry the 08-12 §4 items into any
sprint. The state this preserves is the one on 27291eb59:

```
git grep -rn 'num_shards\|shard_count\|sharding' -- \
  'substrate/graph/retrieval_adapters/*.py' 'substrate/graph/retrieval_substrate.py'
```

returns nothing. This task touches no Turbopuffer code; it only records why.

## The three facts the verdict rests on

**1. Scale.** Production reports `turbopuffer_indexed_row_count: 4837` (read from
`/health` on 2026-09-20 during spec-writing and re-read on 2026-09-22). The
addendum's own sizing line, `docs/specs/turbopuffer-sharding-2026-08-12.md:22`,
gives the per-shard ceiling as **≤1 TB and ≤500M documents**. 4,837 / 500,000,000
= 0.0000097, i.e. **0.00097 percent of a single shard's document capacity**. The
addendum's rule of thumb, `num_shards ≈ ceil(expected_size / 1 TB)`, evaluates to
1 for anything under a terabyte, and its own §5 says "2 shards until data is
>100 GB" — a threshold the corpus is nowhere near. Sharding buys nothing at this
size and its §1 warns that over-sharding costs tail latency.

**2. Subordination.** DuckDB is the source of truth: `/health` reports
`turbopuffer_duckdb_is_sot: true`. The spec's second premise was that
`turbopuffer_production_default_mount` was still `false`; that was true on
2026-09-20 and is **no longer true** — the same read-only `/health` GET on
2026-09-22 returns `turbopuffer_production_default_mount: true`. Recorded so the
next reader is not surprised, and stated plainly: the verdict does not turn on
this flag. Mounting changes *who reads* the namespace, not how much it holds or
how it is rebuilt, and DuckDB remaining the system of record is what makes fact 3
safe.

**3. Reversibility.** The adapter mints a fresh staging namespace per content
digest — `substrate/graph/retrieval_adapters/turbopuffer.py:386`,
`staging = f"{DEFAULT_NAMESPACE}-{content_hash[:12]}"` — and `promote()`
(`turbopuffer.py:549`) only rewrites the `active.json` pointer
(`turbopuffer.py:560`). The SDK's constraint that sharding "can only be
configured on a namespace's inaugural write" therefore binds a *namespace*, not
Antiek: adopting sharding later is one rebuild into a new staging namespace plus
one promote, not a data migration. The spec cited these as `:361` and `:474`; the
code moved to `:386` and `:549` on current main, same code. The 08-12 addendum's
fear — "cannot be retrofitted cheaply (copy-to-new-namespace is the only resize
path)" — describes exactly the path the adapter already takes on every content
change, so the retrofit cost it wanted to avoid is the adapter's normal
operation.

## Reconsider trigger (numeric)

Re-open this decision when **either**:

- `turbopuffer_indexed_row_count` as reported by `/health` exceeds **50,000,000**
  (50M rows, 10 percent of one shard's documented 500M-document ceiling); or
- the active namespace's stored size exceeds **100 GB** (10 percent of the 1 TB
  per-shard ceiling; also the 08-12 addendum's own §5 threshold), as reported by
  Turbopuffer's namespace metadata.

One command settles the first:

```
curl -s https://api.antiek.ai/health | python3 -c "
import json, sys
n = json.load(sys.stdin)['turbopuffer_indexed_row_count']
print(n, 'RECONSIDER' if n > 50_000_000 else 'defer holds')"
```

When a trigger fires, the path is the adapter's existing one: build a sharded
staging namespace through the per-digest rebuild, run the Wedge-1 promotion gate
from `docs/integration_turbopuffer.md` §13 against the *sharded* namespace so the
measurement is taken on what will serve, then `promote()`. Never an in-place
mutation of the active namespace.

## What this does not decide

- No Turbopuffer code changes. Task 1 forbids them and none are needed.
- Nothing about whether Turbopuffer should ever serve as more than a secondary
  index; `docs/integration_turbopuffer.md` owns that and is unchanged.
- Nothing about the mount flag. That it flipped to `true` between 09-20 and
  09-22 is recorded above as an observation, not ratified here.

## How to verify this decision is still true

```
cd /Users/slimydog/Antiek/platform && git fetch origin main -q
git grep -n 'SUPERSEDED' -- docs/specs/turbopuffer-sharding-2026-08-12.md   # names this file
git grep -rn 'num_shards\|shard_count\|sharding' -- \
  'substrate/graph/retrieval_adapters/*.py' 'substrate/graph/retrieval_substrate.py'  # must be empty
curl -s https://api.antiek.ai/health | python3 -c "import json,sys; d=json.load(sys.stdin); \
  print(d['turbopuffer_indexed_row_count'], d['turbopuffer_duckdb_is_sot'], d['turbopuffer_production_default_mount'])"
```

If the second command returns hits, someone executed the superseded 08-12
directives and this decision has been overridden without amendment — treat that
as the finding, not this document.
