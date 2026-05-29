# Attribution trust audit (SPR-04 M1)

Diligence pass BEFORE building the trust layer. Read in full:
`substrate/ad_inventory/attribution.py`, `substrate/attribution/{algorithms,compute}.py`,
`substrate/ad_inventory/{reader_impressions,payout,decisions_log,event_emit}.py`,
the §9.0 classifier (`substrate/contracts/servable.py`,
`substrate/constants.py` §I, `substrate/graph/search.py`,
`substrate/graph/schema.py` documents chunk), and `substrate/event_log/events.py`.

## Finding 0 — there are TWO attribution modules, and the brief names the primitive one

| Module | Shape | Persistence today | Wired into |
|---|---|---|---|
| `substrate/ad_inventory/attribution.py` (BRIEF TARGET) | pure functions taking explicit dicts (`chunk_to_document`, `chunk_to_claim_confidence`, `document_to_source_tier`, load-bearing scores) → `AttributionResult(shares)` | **none** — no event, no version stamp, no audit | `substrate/speak/contributor.py:197` (Speak contributor split, Option B), re-exported by `ad_inventory/__init__.py` |
| `substrate/attribution/compute.py` + `algorithms.py` | reads a synthesis row from DuckDB, resolves chunk→doc→tier, runs A/B/C in parallel, **already emits `PAGE_ATTRIBUTION_COMPUTED`** | event-log JSONL (per-investigation) | `interfaces/research/api/app.py:2953` `/attribution/synthesis/{id}` |

The brief's prose ("computes all three in parallel for A/B since Sprint 16",
"`AttributionAlgorithm` … Option B default") conflates the two: the
*parallel A/B/C compute + event* lives in `substrate/attribution/compute.py`,
but the `AttributionAlgorithm` enum + the three `compute_attribution_option_*`
functions it names live in `substrate/ad_inventory/attribution.py`. I build the
trust layer on the **named** module (`ad_inventory/attribution.py`) — that is
where the algorithm version stamp belongs (it is the module Speak's money path
consumes at `contributor.py:197`), and it is the module with ZERO reproducibility
today. I do NOT duplicate `compute.py`'s synthesis pipeline.

## Finding 1 — reproducibility that EXISTS today

- **`substrate/attribution/compute.py:230-250`** emits a typed
  `PAGE_ATTRIBUTION_COMPUTED` event carrying `algorithm_shares` (A/B/C),
  `claim_count`, `document_count`, stamped with `param_version` +
  `schema_version` by `emit_typed` (`event_log/events.py:282-283`). So the
  *synthesis-page* path has a partial audit record. BUT: it persists only the
  output shares, not the INPUT impression-set / chunk→doc map needed to replay;
  and the version stamp is the global `ANTIEK_PARAM_VERSION`, not an
  algorithm-specific math version.
- **`substrate/ad_inventory/decisions_log.py`** is a fully-worked
  append-only audit-table pattern (defensive `ensure_table`, idempotent insert
  on PK, `load_for_*` queries, canonical schema chunk in `schema.py` V6). This
  is the persistence shape to REUSE, not reinvent.
- **Impressions** (`reader_impressions.py`) are already deterministic
  (`impression_id = imp:{session}:{slot}`) and dedup-stable
  (`dedup_impressions` keeps max focused-dwell). Inputs to attribution are
  therefore already addressable.
- **§9.0 gating already runs on the surfaced path** (`compute.py:160-182`
  drops `restricted_pending_opt_in` docs before computing). Servability is
  DERIVED from `documents.content_class`, never stored (constants.py §I,
  L482-488; `books/servability.py`).

## Finding 2 — what is MISSING (the gap SPR-04 closes)

1. **No algorithm version stamp.** `ad_inventory/attribution.py` has no
   constant identifying the math version. A future tweak to Option B's
   `confidence * (6 - tier)` would silently move every payout with no signal.
   → M3/M5 add `ATTRIBUTION_ALGORITHM_VERSION` + a test that bites on a math change.
2. **No input-preserving, replayable audit record for `ad_inventory` attribution.**
   The decisions log records the *output* RevShareDecisions, but nothing records
   the *attribution inputs* (impression-set ref + the dict args) against the
   algorithm+version that produced the shares. → M3 adds `attribution_audit.py`
   (table mirroring `decisions_log`), and a replay test that re-runs the stamped
   algorithm on the recorded inputs and asserts identical output.
3. **No monetization-eligibility gate distinct from §9.0 servability.**
   `content_class` already encodes both rights AND graph-visibility, but nothing
   reads it as an *earn* gate. `user_owned` = private upload (only owner
   retrieves, `search.py` + schema.py:410). → M2 derives `monetization_eligible`
   from `content_class` (eligible = in public graph; ineligible = `user_owned`).
4. **No chunk-level explainability trace.** Given an asset+period, nothing
   answers "why did this earn this" tracing asset→document→chunk→impression.
   → M4 adds `attribution_explain.py`.
5. **No golden/property lock on the math.** `test_attribution.py` tests the
   `substrate/attribution/` algorithms but NOT `ad_inventory/attribution.py`'s
   three functions, and has no conservation/monotonicity property tests or
   golden fixtures. → M5.
6. **No A/B/C comparison surface over a period.** `compute.py` compares per
   synthesis; nothing emits a per-asset A-vs-B-vs-C table over a period of
   recorded computations. → M6.

## Verdict on M3-M6 scope (honesty: confirm or de-scope)

- **M2** — BUILD. The eligibility gate genuinely does not exist; the
  classification field it derives from (`content_class`) does. Derived, not stored.
- **M3** — BUILD (NOT shrunk). The `PAGE_ATTRIBUTION_COMPUTED` event is
  output-only and globally-versioned; it cannot replay `ad_inventory`
  attribution. A dedicated append-only `attribution_audit` table (reusing the
  `decisions_log` shape) preserves inputs + an algorithm-specific version stamp.
  **Decision: dedicated audit table through `connect_write`, NOT the event log**
  — the event log is investigation-scoped JSONL; an attribution computation is
  keyed by impression-set + period, which maps cleanly onto a queryable table
  and onto replay. Reverse-if: if a future consumer needs attribution audit in
  the unified event trajectory, add a thin `emit_typed` bridge (as
  `event_emit.py` does for RevShareDecision) — the table stays the system of record.
- **M4** — BUILD. No explainability trace exists.
- **M5** — BUILD. No golden/property coverage of the named module.
- **M6** — BUILD. Read-only comparison surface; lives beside the audit module.

## Hard-constraint check

`payout.py` (70/30) and `tools/stripe_connect/` are READ for context only and
are NOT modified by this sprint. The audit layer records and explains; it never
disburses, never writes escrow/payout. The single escrow writer
(`substrate/ip_holders/__init__.py::accrue_escrow`) is untouched.
