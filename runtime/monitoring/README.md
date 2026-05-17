# runtime/monitoring/

Prometheus + Grafana.

## Dashboards (planned)

The five hardware-decision criteria (architecture_notes §6):

1. **Token volume** — by role, by provider, daily/weekly/monthly trend.
2. **Latency** — per-investigation wall clock, broken down by phase.
3. **Multi-tenant pressure** — concurrent investigation count,
   rate-limit-hit frequency.
4. **Skill development** — operator-fluency proxies (deployment
   maintenance events, debugging sessions).
5. **Skill compounding** — per-skill-version quality metric from
   `middleware/backtest/`.

Plus operational dashboards:

- Event log throughput, latency, backlog
- DuckDB write-lock contention
- Acquisition-path success/failure rates per source
- Heartbeat firing reliability
