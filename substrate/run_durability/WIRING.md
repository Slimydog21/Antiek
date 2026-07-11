# Run-durability wiring seam

This package is deterministic domain logic, not another persistence system or
phase state machine. Its `EventLogPort` is intentionally injected. A future
adapter owned by `substrate/event_log` should map the versioned records to the
canonical event envelope and provide atomic expected-sequence append. Reads
must return one run's ordered records without coercing or repairing them.

`orchestration/phase_log` remains the phase-transition authority. It may emit
checkpoint references at existing phase boundaries; this package neither
defines nor advances phases. Checkpoints and completion contain opaque refs
only. Approved brief content, sources, notes, synthesis, and reports remain in
their owning substrates.

An adapter must preserve the event hash and all canonical fields verbatim,
reject a stale expected sequence atomically, and scope reads by both run and
approved-brief identity. It must not swallow validation, CAS, or replay errors.
No filesystem, database, network, provider, budget, or reservation dependency
belongs below this seam.

## Exact adoption points (not implemented in this sprint)

- `substrate/event_log/events.py` is the persistence owner. Its current
  `log_event` API is deliberately best-effort and has no expected-sequence
  CAS, so it is **not** a valid `EventLogPort` as written. The owning lane must
  add an atomic run-scoped adapter rather than make this package write JSONL.
- `runtime/research_runner/host_local.py` is where accepted runs and emitted
  `StepEvent`s can translate to `run_started`, `step_recorded`, and
  `source_fetched`. Source bodies must stay in their owning store; only their
  opaque reference crosses this seam.
- `orchestration/phase_log/log.py` remains the nine-phase authority. Its
  successful existing boundaries may emit the local `CheckpointKind` refs;
  durability must not call `enter`, `exit`, or `verify`, nor infer phases.
- The completion path in the research runner should append `run_completed`
  only after the report has an opaque stable reference and replay shows no
  unresolved floor trip or retryable failure.

The fake adapter proves the pure contract, transition validation, and
kill/reopen equivalence. It does not prove crash-safe production persistence;
that remains blocked on the event-log-owned atomic adapter above.
