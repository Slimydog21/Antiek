"""Archive middleware — synthesis persistence and substrate manifest pinning.

Architecture_notes §4: archive is the SOLE writer to the syntheses
table. This module preserves that invariant from the Researchmaxx
migration. The pure helpers + emit helpers landed in Sprint 2 Day 3-4;
the DB writer ``archive_synthesis_via_db`` and the ``load_synthesis``
reader landed in Sprint 10 day 4-5, once the ``syntheses`` and
``synthesis_substrate_manifest`` tables were created in
``substrate/graph/schema.py``. Both are implemented today.
"""

from .archive import (
    MANIFEST_ENTITY_KINDS,
    ArchiveInputs,
    archive_synthesis_via_db,
    compute_manifest_counts,
    emit_substrate_manifest_written,
    emit_synthesis_archived,
    new_synthesis_id,
    serialize_json_field,
)

__all__ = [
    "MANIFEST_ENTITY_KINDS",
    "ArchiveInputs",
    "new_synthesis_id",
    "serialize_json_field",
    "compute_manifest_counts",
    "emit_synthesis_archived",
    "emit_substrate_manifest_written",
    "archive_synthesis_via_db",
]
