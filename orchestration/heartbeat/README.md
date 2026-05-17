# orchestration/heartbeat/

Periodic autonomous behavior. The thing that makes Antiek a daily-life
agent rather than a code agent — see architecture_notes §3.3.

## Cadences

- **Daily** — ingest new arXiv papers in tracked themes; check active
  investigations for staleness; diff domain skill files to catch
  silent Phase 8 skips early.
- **Weekly** — run the skill-growth audit; generate a token-volume
  report by role and provider; check synthesis consistency against
  backtest cohorts.
- **Monthly** — generate the hardware-decision metrics report; diff
  the four criteria against the previous month; check whether any
  process skills have been derived three times and propose codification.
- **External-event-triggered** — re-evaluate tier classification when
  tracked subjects appear in news; flag syntheses for staleness review
  when contradicting papers publish.

## Discipline

Heartbeats are themselves typed events
(`action_type: heartbeat_fired`). A heartbeat at 8am Tuesday triggering
a skill diff produces a `heartbeat_fired` event followed by downstream
events, all queryable.

## Events emitted

- `heartbeat_fired` — with the cadence, the trigger, and the
  downstream-event correlation ID
