# Durable research execution seam

`durable_execution.py` is the runtime-owned bridge between the run-durability
trace and an effect system. It requires exact lowercase SHA-256 authorization,
opaque references, ordered boundaries, CAS writes, and queryable idempotency
receipts. On restart, receipt lookup reconciles an effect that finished before
its checkpoint was appended. Completion is a stable report reference derived
from the authorized run and committed outcome references.

`durable_worker.py` is a subprocess reference supervisor used to prove real
process kill/reopen behavior against the event-log filesystem adapter. It is
not production wiring.

## Deliberate non-claims

- `HostLocalRunner` and `BrowseLoop` remain unchanged. Their current contracts
  have no approved-brief authorization, resume cursor, queryable effect receipt,
  or stable artifact-reference boundary.
- The reference receipt store proves local POSIX process recovery, not arbitrary
  filesystem power-loss behavior or exactly-once effects from providers that do
  not honor idempotency keys.
- API routes, phase logs, artifact promotion, and Midnight Oil are outside this
  seam. Production adoption must first supply an executor with durable receipt
  lookup and refs-only outputs, then explicitly invoke recovery only after a
  supervisor has established that the prior process died.
