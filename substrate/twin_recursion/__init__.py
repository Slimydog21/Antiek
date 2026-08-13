"""Public durable twin-recursion authority."""

from .ledger import (
    FailureCode,
    SourceRevision,
    TwinConflictError,
    TwinIntegrityError,
    TwinLedgerError,
    TwinRecursionLedger,
    TwinSnapshot,
    UniversalityReport,
)
from .source_registration import (
    TwinSourceCoverage,
    TwinSourceEnvelope,
    TwinSourceEnvelopeError,
    backfill_twin_source_envelopes,
    build_twin_source_envelope,
    project_twin_sources,
    stamp_existing_document,
    verify_twin_source_envelopes,
)

__all__ = [
    "FailureCode", "SourceRevision", "TwinConflictError", "TwinIntegrityError", "TwinLedgerError",
    "TwinRecursionLedger", "TwinSnapshot", "UniversalityReport",
    "TwinSourceCoverage", "TwinSourceEnvelope", "TwinSourceEnvelopeError",
    "backfill_twin_source_envelopes", "build_twin_source_envelope",
    "project_twin_sources", "stamp_existing_document", "verify_twin_source_envelopes",
]
