# middleware/temporal/

Point-in-time queries, staleness, supersession.

## TTL per claim class

`substrate/constants.py:STALENESS_TTL_DAYS` defines time-to-live per
claim class. Market data ages in days; biographical facts age in
decades; fundamental constants effectively don't age. When a claim's
TTL expires, the temporal layer marks it stale and the synthesizer
hedges accordingly.

`scan_graph_edge_staleness(...)` scans the graph's active edges read-only,
preferring the source document's `published_at` timestamp, then an explicit
edge `valid_from`, then `extracted_at`. It emits existing
`graph.staleness.flagged` typed events only; it does not mutate graph rows or
auto-invalidate claims.

## Point-in-time queries

The graph supports "as of timestamp T" queries by filtering events to
those with `timestamp <= T`. This is what makes archived syntheses
re-verifiable: the synthesis recorded under
`ANTIEK_PARAM_VERSION=0.0.1` can be reconstructed by replaying events
up to its creation timestamp.

## Events emitted

- `graph.staleness.flagged` — when an active edge crosses its TTL
- `graph.staleness.resolve` — when a stale flag is resolved
- `supersede` — when a newer claim supersedes an older one
