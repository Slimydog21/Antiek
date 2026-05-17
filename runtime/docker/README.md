# runtime/docker/

Containerization. One container per service; a compose file wires
them together.

## Services (planned)

- `antiek-event-writer` — owns the event log file
- `antiek-duckdb-warden` — owns the DuckDB write lock and serializes
  writes from all writers
- `antiek-heartbeat` — runs the daily/weekly/monthly heartbeat schedules
- `antiek-acquisition-{arxiv,books,urls,rss}` — acquisition workers
- `antiek-interview-web` — interview capture web server
- `antiek-research-api` — research CLI/API surface

## Discipline

Each service has a single responsibility and a single owner process.
Cross-service communication goes through the event log (for state)
or HTTP (for synchronous coordination, mostly via the DuckDB warden).
