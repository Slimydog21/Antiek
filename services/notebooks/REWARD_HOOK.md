# Notebook → Reward Proxy Hook (SPR-08 M7)

**Owner:** `services/notebooks/`
**Cross-reference:** `substrate/behavior/REWARD_PROXY.md` §Worker 2

This document is the contract between the per-document notebook
auto-populator (SPR-08) and the medium-horizon reward proxy worker
(SPR-01 substrate).

---

## The join, in one sentence

For every Tier-1 behavior event on a document, the medium-horizon
reward proxy asks: "did this event end up cited by a notebook block
within 30 days?". The notebook surface is what makes the join
non-empty.

---

## What SPR-08 ships

Three things make the SPR-01 stub real:

1. **`notebook_documents` + `notebook_blocks` populated.** The
   per-document notebook surface auto-creates rows from Tier-1
   events. `notebook_blocks.document_id` is denormalised so the
   reward join is single-table after one filter.

2. **`notebook_blocks.source_event_ids`** carries the originating
   event id(s) for every block. Stored JSON-encoded TEXT[] for
   cross-engine portability (same convention as
   `substrate/behavior/schema.py`'s state/action columns).

3. **`notebook_block_events`** — normalised many-to-many index of
   `(block_id, event_id, event_type)`. The reward worker joins
   against this table rather than parsing the JSON array. The
   auto-populator writes both — the JSON column is the renderer's
   convenience, the table is the worker's join target.

---

## The canonical join

Lives in `substrate/behavior/REWARD_PROXY.md` §Worker 2. Reproduced
here so a SPR-08 maintainer can audit without bouncing files:

```sql
WITH per_doc_refs AS (
  SELECT
    nd.user_id,
    nb.document_id,
    COUNT(*) AS ref_count,
    MIN(nb.created_at) AS first_ref_at
  FROM notebook_documents nd
  JOIN notebook_blocks nb USING (notebook_id)
  WHERE nb.document_id IS NOT NULL
  GROUP BY 1, 2
)
UPDATE behavior_events e
SET reward_proxy_medium = LEAST(refs.ref_count, 5) / 5.0
FROM per_doc_refs refs
WHERE e.user_id = refs.user_id
  AND e.document_id = refs.document_id
  AND e.reward_proxy_medium IS NULL
  AND refs.first_ref_at <= e.timestamp_utc + INTERVAL 30 DAY;
```

### Why this differs from the REWARD_PROXY.md draft

The original SPR-01 draft referenced a `notebooks.tier = 2` filter.
SPR-08's per-doc notebook IS tier 2 by definition (per-document =
tier 2 in master-spec §13.2's three-tier vocabulary). There is no
tier column on `notebook_documents` because the table only stores
tier-2 rows; the join filters implicitly. If SPR-11 (per-theme,
tier 3) lands and shares the same physical tables, a `tier` column
must be added; for SPR-08 the filter is redundant.

### Demoted blocks count

Demoted blocks still appear in `notebook_blocks` (demote is a soft-
delete via `demoted_at`). They participate in the reward join — the
demote itself is signal, not deletion. A future tuning may exclude
demoted blocks from the count or shape them negatively; today they
count equally with visible blocks.

---

## How it gets called

`substrate/behavior/workers/reward_medium.py::run_reward_medium_backfill`
runs the join above. It is invoked:

- By the cron documented in REWARD_PROXY.md (once per hour).
- By the operator command `python -m substrate.behavior.workers.reward_medium`.
- By tests in `services/notebooks/tests/test_reward_hook.py`.

The worker is idempotent because the UPDATE filters on
`reward_proxy_medium IS NULL`. Re-running on the same DB yields the
same row updates (or none if all rows are already populated).

---

## What this hook does NOT do

- It does NOT mutate `behavior_events` itself — that's the worker's
  job. The hook only writes to `notebook_*` tables.
- It does NOT call `emit_behavior_event` to record "I created a
  block from event X". The block→event link IS the record; emitting
  a paper event for it would double-count.
- It does NOT shape the reward by elapsed-time between event and
  block creation. The shaping in REWARD_PROXY.md is reference-count
  only; latency is an explicit future-work item.

---

## Failure modes the hook handles

- **Behavior event whose document_id doesn't match any notebook.**
  The join returns no row → the event's reward_proxy_medium stays
  NULL. Same outcome as the prior stub. No data loss.
- **Notebook block whose source event is older than 30 days at
  populate time.** The join's INTERVAL 30 DAY clause filters it
  out. No reward update; the event is past its window.
- **Source event deleted from `behavior_events`.** SPR-01 events
  are not deleted (only consent-revoked, which keeps the row but
  zeros the consent_version). The hook is therefore stable against
  consent revocation: the row remains queryable for the reward
  join.

---

## Verification gate

```
pytest services/notebooks/tests/test_auto_populate.py -k "reward_hook"
```

Two assertions:

1. After populating a notebook from an event, the canonical join
   returns that block's row when keyed on the event's
   `(user_id, document_id)`.
2. Running `run_reward_medium_backfill` after population sets
   `reward_proxy_medium > 0` on the source events.
