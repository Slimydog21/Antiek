"""Public-notes ingest pipeline (Sprint 22 Phase 3).

Per master-spec §13.2 + §13.9 + Sprint 22 §2 Phase 3:
*"every user's public-facing notes flow into the collective graph
through the §13.9 quality gate (verification + voice-style scoring +
source-tier validation). Pre-onboarded IP-holder content (§9.10)
sits alongside. Operator-curated source corpus continues to seed."*

This module is the orchestrator that CONSUMES `substrate/quality_gate/`
+ writes accepted notes into the collective graph. It does not own
the gate (quality_gate/) nor the storage (collective_graph/); it
sequences the steps:

    CandidateNote
       → run_quality_gate(...)
            verdict = PASS_PUBLIC → write_to_collective_graph
            verdict = REROUTE_PRIVATE → keep_in_private_only
            verdict = REJECT → drop + audit log entry
       → emit ingest event

Pure-functional pipeline; writer is caller-injected. Tests use a
recording stub; production wires a real DB writer.
"""

from .pipeline import (
    IngestEvent,
    IngestEventKind,
    IngestOutcome,
    IngestPipeline,
    Writer,
    run_ingest,
)

__all__ = [
    "IngestEvent",
    "IngestEventKind",
    "IngestOutcome",
    "IngestPipeline",
    "Writer",
    "run_ingest",
]
