# runtime/logging/

Centralized log collection. Application logs, distinct from the
substrate event log.

## The distinction

- **Substrate event log** (`~/.antiek/events.jsonl`) is the audit
  trail. Typed, schema-constrained, replayable. The source of truth
  for what the system did.
- **Application logs** (this module) are the operational trail.
  Free-form, useful for debugging, not the source of truth for system
  behavior.

Confusing the two is a documented failure mode. Operational logs may
be lost or rotated; the substrate event log is preserved.

## Stack (planned)

structlog for application code (structured JSON output), shipped to a
central collector (Loki via Promtail, or Vector → file). The collector
is run via Docker (`runtime/docker/`).
