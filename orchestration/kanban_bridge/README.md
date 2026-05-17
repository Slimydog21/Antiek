# orchestration/kanban_bridge/

Hermes kanban task integration. On-demand investigations enter the
system through here.

## Flow

1. A kanban task transitions to a status that triggers ingestion
   (e.g., "ready for research").
2. The bridge polls or listens for the transition (Hermes-dependent).
3. The bridge launches a `phase_0_intake` event, kicking the phase
   runner into action for that investigation.
4. As phases complete, the bridge updates the kanban task with status
   and links to the archived synthesis.

## Discipline

The bridge never closes a kanban task without verifying that Phase 8
verification passed. Closing a task that claims compounding without
verified compounding is exactly the failure mode this architecture is
designed to prevent.
