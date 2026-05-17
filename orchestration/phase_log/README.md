# orchestration/phase_log/

Records every phase entry, exit, and verification status per
investigation. This is the table that `orchestration/audit/` queries
when deciding whether a Phase 8 was substantive or rhetorical.

## Schema

```
(investigation_id, phase, entered_at, exited_at, verified, verification_metadata)
```

`verified` is a boolean. `verification_metadata` is a JSON blob
containing whatever the phase-specific verifier produced (for Phase 8,
the file-diff result).

## Discipline

The phase log is append-only at the (investigation_id, phase, transition)
level. A phase that's been entered may be re-exited (re-runs are valid)
but the prior exit is not erased — the log preserves the full trajectory.
