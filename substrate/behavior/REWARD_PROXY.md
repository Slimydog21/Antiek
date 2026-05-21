# Reward Proxy Backfill Workers

**Status:** SPR-01 M5. Immediate worker is real; medium + deep are
documented stubs awaiting Wave 2 emission + Sprint-17/22 tables.

The behavior store reserves three reward-proxy columns on every
row — `reward_proxy_immediate`, `reward_proxy_medium`,
`reward_proxy_deep`. They are nullable at write; three async
workers populate them as evidence accumulates.

This file is the contract each worker MUST honour. The worker code
in `workers/` is the implementation; this document is the spec
those implementations are measured against.

---

## Design — why three columns

Reward signal compounds across horizons. The same behavior event
(a cross-doc link surfacing, say) can produce:

- An immediate signal: was it clicked within 5s?
- A medium signal: did the clicked target appear in a Tier-2
  notebook within 30 days?
- A deep signal: did that notebook feed a published deliverable?

If we collapse to one column we lose the gradient that on-policy
RL needs. Three columns lets the policy optimiser weight the
horizons separately and lets the operator audit "are we training
on signal A or B?"

All three are floats (not bools) to admit shaped signals — a
half-second click is more strongly positive than a 4.9s click;
a 100-word notebook reference is stronger than a 10-word one. The
exact shaping is a worker-internal choice; the worker MUST
document its mapping in its own module docstring.

---

## Worker 1 — `reward_immediate.py`

**Horizon:** Same session, ≤ 5 s elapsed.

**State today:** REAL IMPLEMENTATION. Only requires `behavior_events`,
which exists post-M2. Runnable against synthetic data.

**Signal:** For each `cross_doc_link_surfaced` row, look for a
matching `cross_doc_link_clicked` row in the same `session_id`
within 5 seconds. If present, set
`reward_proxy_immediate = 1.0` on the surfaced row; if absent,
`= 0.0`. (Dismissals also set `0.0` explicitly via a
`cross_doc_link_dismissed` row — the worker handles both.)

**Join query (canonical):**

```sql
WITH surfaced AS (
  SELECT event_id, session_id,
         json_extract_string(action, '$.link_id') AS link_id,
         timestamp_utc
  FROM behavior_events
  WHERE event_type = 'cross_doc_link_surfaced'
    AND reward_proxy_immediate IS NULL
),
clicked AS (
  SELECT session_id,
         json_extract_string(state, '$.link_id') AS link_id,
         MIN(timestamp_utc) AS first_click_at
  FROM behavior_events
  WHERE event_type IN ('cross_doc_link_clicked', 'cross_doc_link_dismissed')
  GROUP BY session_id, link_id
),
joined AS (
  SELECT s.event_id,
         EXTRACT(EPOCH FROM (c.first_click_at - s.timestamp_utc)) AS dt
  FROM surfaced s
  LEFT JOIN clicked c
    ON s.session_id = c.session_id AND s.link_id = c.link_id
)
UPDATE behavior_events
SET reward_proxy_immediate = CASE
  WHEN j.dt IS NULL OR j.dt > 5 OR j.dt < 0 THEN 0.0
  ELSE 1.0
END
FROM joined j
WHERE behavior_events.event_id = j.event_id;
```

**Shaping (today):** Binary 0/1. Future work may shape the
positive case to `1 + exp(-dt/τ)` for sub-5s clicks, but the spec
calls for the simple binary today.

**Cron cadence:** Once per minute when behavior_events is non-empty.
The worker is idempotent: it operates on rows where
`reward_proxy_immediate IS NULL`.

## Worker 2 — `reward_medium.py`

**Horizon:** ≤ 30 days, requires Tier-2 (per-document) notebook references.

**State today:** STUB. Reads from `notebooks` and `notebook_blocks`
tables that are scaffolded but empty until SPR-08 emits into them.

**Signal:** For each behavior event whose associated
`document_id` later (within 30 days) appears in a Tier-2
notebook block belonging to the same `user_id`, set
`reward_proxy_medium > 0`. Shaping is by reference count
(`min(N, 5) / 5`) so a referenced-once doc gets 0.2, a
referenced-five-times doc gets 1.0.

**Join query (canonical, will execute when notebooks land):**

```sql
WITH per_doc_refs AS (
  SELECT
    nb.owner_user_id AS user_id,
    nb_blocks.document_id,
    COUNT(*) AS ref_count,
    MIN(nb_blocks.created_at) AS first_ref_at
  FROM notebooks nb
  JOIN notebook_blocks nb_blocks USING (notebook_id)
  WHERE nb.tier = 2
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

**Stub behaviour:** The worker checks `information_schema.tables`
for `notebooks` + `notebook_blocks`. If either is missing or
empty, it logs a one-line breadcrumb and exits cleanly. This is
the spec's "handles empty gracefully" requirement.

**Cron cadence:** Once per hour. The 30-day window means we cannot
finalise a row's medium reward until 30 days post-emit, so the
worker re-runs continually.

## Worker 3 — `reward_deep.py`

**Horizon:** Variable; requires a `deliverables` table that the
spec describes but Sprint 17+ will create. The notebook referenced
in the medium signal must itself be cited by a *published*
deliverable.

**State today:** STUB. Reads from `notebooks`, `notebook_blocks`,
and `deliverables`. The `deliverables` table is a Sprint 17+
artifact (creation surface lock-in); today it does not exist.

**Signal:** For each behavior event whose associated `document_id`
is referenced by a notebook that is in turn cited by a
**published** `deliverables` row, set `reward_proxy_deep > 0`.
Shaping is binary today (the publication is the threshold);
future work may shape by deliverable reach.

**Join query (canonical, will execute when deliverables land):**

```sql
WITH deep_refs AS (
  SELECT
    nb.owner_user_id AS user_id,
    nb_blocks.document_id
  FROM deliverables d
  JOIN deliverable_citations dc USING (deliverable_id)
  JOIN notebooks nb ON dc.notebook_id = nb.notebook_id
  JOIN notebook_blocks nb_blocks USING (notebook_id)
  WHERE d.published_at IS NOT NULL
)
UPDATE behavior_events e
SET reward_proxy_deep = 1.0
FROM deep_refs r
WHERE e.user_id = r.user_id
  AND e.document_id = r.document_id
  AND e.reward_proxy_deep IS NULL;
```

**Stub behaviour:** Same pattern as the medium worker — probe
`information_schema.tables`, log + exit if dependencies are
missing.

**Cron cadence:** Once per day. Publication events are rare;
hourly is wasteful.

---

## Summary of state — SPR-01 closeout

| Worker | Real? | Reason |
|--------|-------|--------|
| `reward_immediate` | YES | Only reads `behavior_events`. |
| `reward_medium` | NO (stub) | `notebooks` empty until SPR-08. |
| `reward_deep` | NO (stub) | `deliverables` table not yet created (Sprint 17+). |

Stubs include the canonical join queries above so a future
maintainer can swap in the real logic without re-deriving the
join shape. The rigor block #1 mandate ("do not write a
placeholder that returns plausible-but-fake numbers") is the
reason the medium/deep workers no-op rather than estimate.
