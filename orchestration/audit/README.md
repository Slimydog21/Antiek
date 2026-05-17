# orchestration/audit/

Compounding-skill verification, Phase 8 enforcement.

## What it does

Reads the event log and the skill files; emits alerts when a Phase 8
was logged as executed but the skill files didn't grow. This is the
mechanical verification that replaces prose-enforced "the system
compounds."

## Integration

`orchestration/audit/` consumes from `compounding/verification/` for
the diff machinery and writes its findings into the event log
(`action_type: audit_finding`). The findings surface in the weekly
heartbeat-generated audit report.

## Discipline

An audit finding that Phase 8 didn't grow the skill files **blocks
the kanban bridge from closing the corresponding task**. This is the
hard interlock — see architecture_notes §2.2.
