# orchestration/

The autonomous-behavior and phase-management layer. This is where the
"prose enforcement → code enforcement" migration pays down its debt.

## Modules

- **`phase_runner/`** — State machine for the 9-phase autonomous
  research protocol. Phase transitions are explicit function calls,
  not implicit model behavior. The Researchmaxx audit identified
  prose-enforced phase orchestration as "the single biggest gap in
  the architecture"; this module is the fix.
- **`phase_log/`** — Records every phase entry, exit, and verification
  status per investigation. Phase 8 cannot be marked complete unless
  `phase_log[8]["verified"] == True` based on a mechanical diff of the
  skill files showing growth.
- **`kanban_bridge/`** — Hermes kanban task integration. On-demand
  investigations enter through here.
- **`heartbeat/`** — Periodic autonomous behavior. Daily ingestion,
  weekly skill-diff audit, monthly hardware-decision metrics report.
  See architecture_notes §3.3. Heartbeats are themselves typed events
  in the log, so autonomous behavior is auditable in the same way
  investigation behavior is.
- **`audit/`** — Compounding-skill verification, Phase 8 enforcement.
  Reads the event log and the skill files; emits alerts when a Phase 8
  was logged as executed but the skill files didn't grow.

## Non-negotiables

- Phase transitions are code, not prose.
- Phase 8 verification is mechanical (file diff), not rhetorical.
- Heartbeats emit typed events. Autonomous behavior is auditable.

See architecture_notes §2.2 and §3.3.
