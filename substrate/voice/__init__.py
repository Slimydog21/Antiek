"""Voice-note region anchor primitive (Sprint SPR-02, Wrestle Evolution).

Substrate-only. Adds ``voice_note_anchor`` keyed by
``(document_id, page, bbox)`` plus an optional ``chunk_id`` derived
from the bbox at write time. The UI that records and renders these
anchors lands in SPR-05.

Public surface:
  - ``CHUNKER_VERSION`` — source-of-truth constant the schema records
    on every anchor row. Bumping this triggers the re-chunk worker.
  - ``anchor_schema`` — DDL + table list.
  - ``anchor_api.create_anchor``, ``get_anchors_on_page``,
    ``get_anchor_by_voice_note``, ``resolve_chunk_for_bbox``.
  - ``migrate.apply`` — idempotent migration runner.
  - ``workers.rechunk_anchors`` — re-resolves chunk_id when the
    chunker_version has moved.

See ``SCHEMA_NOTES.md`` for the 30% overlap threshold rationale and
the chunker_version source-of-truth.
"""

# Source of truth for the chunker_version column. The re-chunk worker
# compares each anchor row's stored chunker_version against this
# constant; mismatch → re-resolve.
#
# Bumping rules:
#   - Bump on any change to the chunker that could alter chunk
#     identity for the same input (e.g., a regex change, a
#     max_chunk_tokens default change, a new section-aware mode).
#   - Do NOT bump for non-identity-affecting changes (e.g., adding a
#     log line, refactoring without behavior change).
#
# Why a string constant here and not a hash of the chunker module:
# the worker must be able to reason about "is X older than Y";
# semver-style strings give a stable, comparable identity. Hashing
# the chunker module would make every refactor look like a chunker
# upgrade, defeating the purpose.
CHUNKER_VERSION: str = "1.0.0"


__all__ = ["CHUNKER_VERSION"]
