"""Per-document notebook service (Wrestle Evolution SPR-08).

Owns the per-(user_id, document_id) notebook surface mounted by the
reading app at ``/wrestle/<document_id>/notebook``.

Module map
----------
- ``schema`` — DDL + idempotent migrate command.
- ``blocks`` — closed block taxonomy + Tier-1 event→block mapping.
- ``persistence`` — JSON-format-now / .antiek-format-later abstraction.
  SPR-09's swap point: replace the ``JSONPersistence`` writer; do not
  touch the surface.
- ``auto_populate`` — server-side worker; reads Tier-1 behavior events
  via ``substrate.behavior.export.query_raw`` (operator-only path) and
  upserts blocks idempotently.
- ``reward_hook`` — wires the per-doc-notebook population back into
  ``substrate.behavior.workers.reward_medium`` so the canonical
  behavior_event → notebook_block join in REWARD_PROXY.md can run.

Substrate boundary
------------------
This package READS Tier-1 events (operator role) but never mutates
``behavior_events`` directly — emits go through
``substrate.behavior.api.emit_behavior_event``. The auto-populator
writes ONLY to ``notebook_documents`` + ``notebook_blocks``.
"""

from .blocks import (
    BLOCK_TAXONOMY_VERSION,
    BLOCK_TYPES,
    BlockType,
    EVENT_TYPE_TO_BLOCK_TYPE,
    event_type_for_block,
)
from .persistence import (
    JSONPersistence,
    NotebookPersistence,
    NotebookRecord,
    BlockRecord,
)
from .schema import (
    MIGRATION_FILES,
    init_notebooks_schema,
    init_notebooks_schema_at_path,
)

__all__ = [
    "BLOCK_TAXONOMY_VERSION",
    "BLOCK_TYPES",
    "BlockRecord",
    "BlockType",
    "EVENT_TYPE_TO_BLOCK_TYPE",
    "JSONPersistence",
    "MIGRATION_FILES",
    "NotebookPersistence",
    "NotebookRecord",
    "event_type_for_block",
    "init_notebooks_schema",
    "init_notebooks_schema_at_path",
]
