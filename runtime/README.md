# runtime/

Deployment configuration. The build runs on rented infrastructure for
9–12 months; this directory holds everything needed to bring the
substrate up on a VPS (Hetzner, DigitalOcean, equivalent) with 16–32
CPU cores, 64–128 GB RAM, 1–2 TB NVMe storage.

## Modules

- **`docker/`** — Containerization. One container per service; a
  compose file wires them together. Services include: event-log
  writer, DuckDB warden (the write-coordinator), heartbeat orchestrator,
  acquisition workers, interview capture web server.
- **`monitoring/`** — Prometheus + Grafana. Dashboards for the five
  hardware-decision criteria (token volume, latency, multi-tenant
  pressure, skill development, skill compounding). Dashboards are
  the operator's primary view into whether the rental path remains
  correct or whether ownership becomes defensible.
- **`logging/`** — Centralized log collection. Application logs are
  distinct from the substrate event log; the substrate event log is
  the audit trail, application logs are the operational trail.
- **`deployment/`** — Configuration for VPS or local runtime. Includes
  systemd units, nightly backup scripts (target: S3-compatible like
  Backblaze B2 or Wasabi), and the bootstrap procedure.

## Storage layout

```
~/.antiek/
├── research_graph.duckdb     # graph state (derived; replayable)
├── duckdb.lock               # write coordinator (see substrate decisions)
├── events.jsonl              # append-only event log (source of truth)
├── events.parquet            # periodic compaction for query efficiency
├── interviews/               # content-addressed audio + transcripts
└── skills/{process,verification}/   # non-domain skills

~/.hermes/skills/research/
├── quantum-knowledge/
├── defense-knowledge/
├── ai-infrastructure-knowledge/
└── semiconductor-knowledge/
```

The event log is the recoverable source of truth. The DuckDB file can
be reconstructed by replaying events. Nightly backups go to
S3-compatible storage; restoring from backup is a documented procedure.

## Local backends (deferred)

No local model hosting in this build. The dispatch router has the
abstraction in place; adding a local backend later is one new entry
in `substrate/dispatch/config.yaml` and one new module behind the same
interface.
