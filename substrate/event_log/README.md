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
