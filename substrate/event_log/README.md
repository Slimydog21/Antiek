# substrate/event_log/

Typed, append-only event log. The source of truth for the entire system.

Every action that mutates state — every ingest, extraction, retrieval,
synthesis attempt, skill update, heartbeat firing, context-pack assembly —
is captured here. Graph state in `substrate/graph/` is derived by
replaying these events; if the DuckDB file is lost, the events file
rebuilds it.

## Event shape

```
(event_id, timestamp, investigation_id, phase, role,
 action_type, payload, parent_event_id, parameter_version)
```

## Storage

- Live: `~/.antiek/events.jsonl` (append-only JSONL)
- Compacted: `~/.antiek/events.parquet` (periodic, for query efficiency)

## Action vocabulary

Enumerated in `substrate/schemas/actions.py`. The minimum stable set
is in `docs/architecture_notes.md` §2.1.

## Contract

Writes are append-only. Readers may consume the JSONL in stream or
batch-query the Parquet. No code path outside this module is permitted
to mutate the log; even compaction is read-then-write to a new file
followed by atomic rename.

## Worker identity + token-burn telemetry (SPR-01, antiek-yegge-execute)

Two additions, schema version 27 → 28:

- **`worker.identity`** — a NEW typed event recording the registration of a
  first-class worker (by the future worker registry, SPR-04). Carries
  `worker_id` + `parent_worker_id` + `role` + `session_id` + `spawn_kind`
  (one of `subprocess` / `asyncio_task` / `thread` / `role_invocation` /
  `variant`) + optional `expected_lifetime_s` + `context_hash`. event_log
  stores `worker_id` verbatim — UUID-v7 validity is SPR-04's job.

  Emit/query API:

  ```python
  from substrate.event_log import emit_worker_identity, query_worker_identity

  emit_worker_identity(
      "inv-1", worker_id="0192-...", role="extractor",
      session_id="sess-1", spawn_kind="asyncio_task",
  )
  rows = query_worker_identity("inv-1", role="extractor")
  ```

- **token-burn telemetry** — NOT a new event. `DISPATCH_CALL` is already the
  canonical per-LLM-call token+cost event (`substrate/coordination/cost_view.py`
  reads every cent off `DispatchCallPayload.cost_usd`), so a separate
  `token_burn` event would fork the convention. Instead `DispatchCallPayload`
  gains five OPTIONAL fields (default-None/0 so existing emitters + cost_view
  reads stay byte-identical): `cached_input_tokens`, `task_id`, `parent_run_id`,
  `feature_label`, `session_id`. SPR-05's dashboards query the enriched
  `DISPATCH_CALL` rather than a duplicate. Operator decision 2026-07-02.

The migration is an explicit no-op (append-only JSONL/Parquet needs none):
`substrate/event_log/migrations/spr_01_token_burn_worker_identity.py`.
