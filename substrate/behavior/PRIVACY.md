# Behavior Store — Privacy Posture

**Status:** Locked 2026-05-21 (Antiek master spec v3 sharpening).
**Module:** `substrate/behavior/` — the Tier-1 behavior store.
**Subject to:** Master spec §13.3 (DP shuffler), §13.7 (Trust Center), §16.2 (REJECT canon).

This document is the source of truth for what the behavior store
does and does not do with user data. A future maintainer must be
able to read this without reconstructing the rationale from chat
logs.

---

## 1. Posture (verbatim, locked 2026-05-21)

> **Delete future events on opt-out; trained models persist.**

This is the industry-standard pattern (Apple, Google, OpenAI, all
operate under variants of this). The trade-offs are:

- Pro: Models that have learned from a user's data continue to be
  useful for that user (and all other users) even after that user
  opts out. The user's marginal contribution to the next epoch's
  training data is zero, but their contribution to past epochs is
  baked into model weights.
- Pro: We never need to retrain to honour an opt-out, which would
  be operationally prohibitive at scale and lossy for every other
  user.
- Con: Politically sensitive. A future EU regulator may rule that
  "trained models persist" is insufficient under GDPR Art. 17
  (right to erasure). The open question is tracked on the master
  spec.

**Open question (master spec, row "EU regulator action on trained
models"):** Does the EU's emerging AI Act require model retraining
on opt-out for personal-data signals? If yes, our posture is the
US/UK position and we will need a per-jurisdiction policy.

## 2. What the substrate enforces (today)

Three guarantees, all testable:

### 2.1 Opt-in by default
A user has NO active consent row by default. Without a row, every
`emit_behavior_event` call is a silent no-op — no row lands in
`behavior_events`. This is enforced in `consent.py::is_consent_active`
and consumed by `api.py::emit_behavior_event`.

The emit API returns the same opaque event id either way, so the
caller cannot infer consent state through the return value (no
side-channel leak).

### 2.2 Revocation stops future writes; existing rows persist
`consent.py::revoke_consent` updates the user's consent row to set
`revoked_at`. Every subsequent emit for that user is a no-op until
they re-grant.

Existing rows in `behavior_events` are NOT deleted on revoke. This
is the locked policy verbatim from §1.

If a future Trust Center surface (Sprint 22) wants to provide a
"delete my future events going forward, even if some are still in
the queue" guarantee, a separate cron job can `DELETE FROM
behavior_events WHERE user_id = X AND timestamp_utc >
revocation_time`. The substrate does NOT do this today; it does
the stronger guarantee of "no future writes".

### 2.3 Training-data egress goes through the DP shuffler
Every row that leaves `behavior_events` for training-corpus use
MUST pass through `export.py::export_training_batch`, which:
- Reads only rows where `dp_shuffler_batch_id IS NULL` (so the
  same row cannot enter two corpora).
- Applies Fisher-Yates ordering perturbation.
- Applies Laplace noise to `timestamp_utc` with scale `1/ε`
  seconds.
- Stamps each contributing source row with the new `batch_id`.

Direct table queries on `behavior_events` are operator-only via
`export.py::query_raw`, which requires a caller-supplied
`operator_check` callback. The default refuses everything; a
forgotten check is safe.

## 3. ε and δ

| Parameter         | Value | Source / rationale |
|-------------------|-------|--------------------|
| Surface name      | `behavior_training_export` | Single registered surface for behavior egress. |
| Sensitivity class | `medium` | Per `epsilon_registry.SENSITIVITY_BUDGETS`. Cap = 2.0 ε/day. |
| Per-batch ε       | **1.0** | Half the daily cap — leaves headroom for a second daily export under the same surface. |
| δ                 | **1e-9** | Negligible per master-spec §13.3 ("expert consensus band"). Included for future composition; the perturbation is pure-ε. |
| Cap (registry)    | 2.0 ε/day | Enforced by `epsilon_registry`. Refused with `ValueError` at `export_training_batch` if exceeded. |

The choice of ε = 1.0 sits inside the master-spec §13.3 band of
"various degrees of better than nothing" (ε ∈ [1, 10]) on the
strong end. The §16.2 hard cap is ε > 10 forbidden; we are
comfortably below it.

**Citation:** master-spec §13.3 (DP shuffler), reflected in
`substrate/dp_shuffler/epsilon_registry.py::SENSITIVITY_BUDGETS`
and verified by the test
`test_sensitivity_budgets_match_master_spec`.

## 4. Perturbation mechanics

Two perturbations, both pure-ε:

### 4.1 Ordering perturbation (Fisher-Yates shuffle)

The output rows are produced in `random.shuffle()` order. For any
non-trivial batch (n ≥ 2), the probability of preserving the input
ordering is 1/n!. The quantitative test floor is set at "at least
30% of input-adjacent pairs inverted" for n = 1000 (the M3 test).

The 30% floor is far below the expected ~50% for a uniform shuffle
but well above the noise level a non-shuffler would produce; it's
a defensive lower bound that catches a regression where the
shuffle becomes a no-op.

### 4.2 Timestamp jitter (Laplace mechanism)

Each row's `timestamp_utc` gets one i.i.d. sample from
Laplace(0, 1/ε) seconds. For ε = 1.0 the noise has scale 1.0 s,
expected absolute value ln(2) ≈ 0.69 s. Across n = 1000 rows the
empirical standard deviation will be √2 / ε ≈ 1.41 s. The M3 test
asserts the sample std-dev exceeds 0.5 s (a generous lower bound
catching a regression to zero jitter).

The Laplace mechanism provides ε-DP for the timestamp column. The
two perturbations compose to (ε_total = ε_order + ε_timestamp) by
the additive composition theorem, but the ordering is itself a
post-processing of the timestamp jitter (sort by jittered
timestamp would re-shuffle), so we account the combined
guarantee at ε = 1.0 for a single export batch.

## 5. What the substrate does NOT do (yet)

- **Pseudonymisation.** Identifying fields (`user_id`,
  `session_id`, `document_id`) pass through unchanged. The
  cryptographic shuffler from Mozilla Prio is a later
  integration; today's `export.py` is the protocol-shape only.
  See `substrate/dp_shuffler/shuffler.py` for the same note.
- **Pre-training scrubbing.** ML pipelines that consume the
  exported batch are responsible for any further processing
  (chunking, embedding, filtering).
- **Retroactive deletion of trained-into events.** Out of scope by
  the locked policy in §1.
- **Cross-user aggregation under DP.** Single-user signals only
  for now; federation is Sprint 30+.

## 6. Where the gates fail loud

| Failure mode | What happens |
|--------------|--------------|
| Unknown event_type emitted | `InvalidEventType` raised at API boundary (taxonomy.py). |
| Malformed state/action | `SchemaValidationError` raised at API boundary. |
| Export with ε above daily cap | `ValueError` from `_check_registry_allows`. |
| Export with ε ≤ 0 | `ValueError` from `_shuffle_and_jitter`. |
| Non-operator calls `query_raw` | `OperatorRoleRequired` (PermissionError). |
| Source row already shuffled | `WHERE dp_shuffler_batch_id IS NULL` excludes it; no double-counting. |

---

**Verbatim posture:** Delete future events on opt-out; trained
models persist. Locked 2026-05-21.
