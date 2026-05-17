# substrate/graph/

DuckDB-backed knowledge graph. Typed nodes and edges. Schema, ingest,
search, traverse.

## Contents

- `schema.sql` — DDL for nodes, edges, chunk index, embedding index.
- `ingest.py` — Applies events to update the graph. Consumes the event
  log; never the inverse.
- `search.py` — Embedding-based candidate retrieval plus typed
  filtering. The cross-domain connector role uses this to surface
  candidates before any LLM step.
- `traverse.py` — Multi-hop traversal for the connector role.

## Discipline

The graph is *derived* state. Never mutate the DuckDB file directly
from application code; emit an event, let `ingest.py` apply it. This
is what makes the event log replayable and the graph reconstructable.

## Write coordination

All writers go through the lock at `~/.antiek/duckdb.lock` — see
`runtime/deployment/` and architecture_notes §2.3.
