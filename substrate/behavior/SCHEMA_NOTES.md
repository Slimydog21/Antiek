# Schema Notes — Behavior Store vs. event_log

**Audience:** Future maintainers + the SPR-01 rigor #4 (diligence)
gate. Read this before re-architecting either store.

The Antiek substrate has *two* event streams now:

| Stream | Location | Purpose | Privacy regime |
|--------|----------|---------|----------------|
| `event_log` | `substrate/event_log/` (Parquet, append-only JSONL → Parquet) | IP / audit trajectory — what the substrate did | None (operator-internal) |
| `behavior_events` | `substrate/behavior/` (DuckDB) | RL training data — what the operator did | Opt-in consent + DP shuffler on export |

This document explains where the schemas overlap (intentional
reuse), where they diverge (intentional), and why a maintainer
should not be tempted to merge them.

---

## 1. Why two stores, not one

The rigor #2 steelman ("single events table") is recorded in the
SPR-01 handoff. The short version:

- `event_log` rows describe orchestrator/role/grader actions and
  carry policy_id, parent_event_id, role, phase. They are the
  trajectory substrate Loop-2 RL trains *the substrate* on.
- `behavior_events` rows describe operator-surface actions —
  highlights, voice notes, AI prompts, link clicks. They are the
  on-policy data Loop-3 RL trains *for the operator's reading
  workflow* on.
- The privacy regimes are different: `event_log` is operator-
  internal (no DP); `behavior_events` is opt-in + DP-shuffled
  before egress. Mixing them in one table couples the two regimes,
  which is bad for both.
- The schemas mostly differ — `event_log` has no notion of
  `state/action/outcome/reward_proxy_*`; `behavior_events` has
  no notion of `phase/role/policy_id/parent_event_id`.

Keeping them separate keeps each schema honest. Re-merging would
require a "regime" column and consistent CHECK constraints
everywhere, with no upside.

## 2. Reuses (intentional)

The behavior store deliberately mirrors event_log conventions
where the column meaning agrees:

| Concept | event_log | behavior_events | Same? |
|---------|-----------|-----------------|-------|
| Opaque event id | `evt-<12hex>-<ms epoch>` | `evt-<12hex>-<ms epoch>` | Yes; identical format from `event_log.events._new_event_id()` |
| Timestamp format | ISO 8601 UTC with `Z` suffix | DuckDB `TIMESTAMP` column | Different (see §3) |
| Storage of structured payloads | JSON string in `payload` | JSON string in `state`/`action`/`outcome` | Yes; same Researchmaxx VARIANT-deferral convention from `graph/schema.py` |
| UUID generation | `uuid.uuid4().hex[:12]` | `uuid.uuid4().hex[:12]` | Yes |
| Write coordinator | `runtime/db_lock.connect_write` | `runtime/db_lock.connect_write` | Yes; same flock |
| Append-only discipline | JSONL → Parquet seal | DuckDB INSERT, no UPDATE except reward backfill + dp_shuffler_batch_id stamp | Same intent (append-only logically) |

## 3. Divergences (intentional)

Where we diverge, the reasoning is noted here:

### 3.1 Storage backend

- `event_log` is **JSONL → Parquet** because it's an investigation-
  scoped trajectory that the operator wants to ship to prime-rl /
  verifiers. Parquet is the format that toolchain consumes.
- `behavior_events` is **DuckDB-native** because (a) it's
  cross-session, cross-document — there's no investigation-scoped
  partition to seal to; (b) the reward-proxy backfill workers need
  efficient UPDATEs (DuckDB) not new file appends (Parquet); and
  (c) it joins to `notebooks`, `deliverables`, `documents` in the
  graph DB.

### 3.2 Timestamp representation

- `event_log` stores ISO 8601 strings with `Z` (`"2026-05-21T12:34:56Z"`).
- `behavior_events` stores DuckDB `TIMESTAMP` (typed) because (a)
  we index on it and want range queries to use the column-store
  fast path, and (b) the DP shuffler arithmetic
  (`timestamp + jitter_seconds`) is more natural on a typed column.

The two formats are interconvertible; queries that need to join
across the two stores (rare) just cast.

### 3.3 Schema columns

`event_log` has columns the behavior store does not need:
`investigation_id`, `synthesis_id`, `phase`, `role`, `policy_id`,
`parent_event_id`, `param_version`, `schema_version`. These are
all orchestrator-internal concepts that don't fit Wave 2 emission.

The behavior store has columns event_log does not:
`session_id`, `state`, `action`, `outcome`,
`reward_proxy_immediate/medium/deep`, `consent_version`,
`dp_shuffler_batch_id`. These are all RL-shaped concepts that
don't fit IP/audit.

### 3.4 No FK constraint on `documents`

The behavior store names `document_id` as a "FK target" per the
sprint spec, but the table-level FK constraint is intentionally
NOT declared in `0001_behavior_store.sql`. Reasons:

- DuckDB's FK enforcement is partial (no cascading,
  index requirements). Adding a constraint creates work for the
  migration runner without preventing many failure modes.
- The `documents` table may not exist when the behavior migration
  runs (it's owned by `substrate/graph/`). Forcing init order
  adds coupling for no real safety.
- Application-layer code (the emit API + workers) is responsible
  for setting `document_id` to a value that *does* match a
  `documents.document_id` when one exists. Wave 2 surfaces are the
  enforcer of this; if they pass a bogus id, it shows up as a
  dangling reference at backfill time, which the worker logs.

### 3.5 `users` table — does not exist

The sprint spec lists "users table exists with FK target" as an
external dependency. As of SPR-01 the Antiek substrate is
single-operator and has no `users` table — the convention is the
constant `__operator__` (see `substrate/multi_user/auth.py`).
`behavior_events.user_id` is a `TEXT` column that defaults to
this constant via the emit API; multi-user lands at Sprint 22+
without a schema change on the behavior store (the column shape
is already right; an application-layer `users` table can be added
then with the FK pointing at it).

The dependency is therefore "not blocked, but the FK is application-
enforced today, not DDL-enforced". Flagged in the SPR-01 handoff.

## 4. What to read before changing either schema

- `substrate/event_log/events.py` — emit / seal / query.
- `substrate/schemas/events.py` — typed payload union.
- `substrate/behavior/schema.py` — DDL + migrate runner.
- `substrate/behavior/api.py` — the emit boundary.
- `substrate/behavior/PRIVACY.md` — the policy that justifies the
  divergent regime.
- `docs/architecture_notes.md` §2 (event-stream discipline),
  §9 (wrestling loop) — the master-spec roots.

If a change crosses both stores (e.g., "thread an event_id
across regimes"), the right move is usually to *not* — keep the
two trajectories independent and join in the analyst layer.
