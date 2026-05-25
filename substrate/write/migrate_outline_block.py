"""Migrate section_blocks → outline_blocks (specs/write/ SPR-01 M6).

The OutlineBlock layer (``outline_blocks``) supersedes the older
``section_blocks`` table. This migration copies every existing
``section_blocks`` row into ``outline_blocks`` **without loss and
idempotently**, so existing CreationStudio deliverables keep working:

- The original ``(block_kind, block_id)`` is preserved in
  ``source_block_kind`` / ``source_block_id`` (auditable, reversible).
- ``provenance_kind`` is inferred from the original ``block_kind``:
    insight / open_question / claim → ``graph_node`` (node_id = block_id).
        These were always node/claim references in the old model.
    operator_note                   → ``user_authored`` (node_id null).
        Operator notes have no graph node; they are user-originated. The
        old model stored only a ``block_id`` (not the text), so the
        migrated block carries a placeholder content marker and a
        metadata note — we do NOT fabricate a node reference.
- Ordering (``block_index``) is preserved.

Idempotency: each migrated row gets a content-addressed
``outline_block_id`` derived from ``(section_id, block_kind, block_id)``,
so a second run finds the row already present and skips it (``place_block``
with ``on_conflict='ignore'``). Flat sections need no migration — they
are already a depth-1 outline (see ``outline.build_outline_tree``).

Honesty note (rigor #1): this has been verified against a *synthetic
populated copy* (a DB seeded with representative deliverables/sections/
section_blocks), not against operator production data, which this agent
cannot access. The migration is idempotent and non-destructive
(``section_blocks`` is read-only here and left intact), so re-running on
real data is safe; the handoff records this boundary.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    from ...runtime.db_lock import LockedConnection
    from ..graph.ops import content_addressed_id
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.graph.ops import content_addressed_id  # type: ignore[no-redef]

from .outline_block import place_block

# Original block_kind → (provenance_kind, new block_kind, node-backed?).
_KIND_MAP: dict[str, tuple[str, str, bool]] = {
    "insight": ("graph_node", "insight", True),
    "open_question": ("graph_node", "open_question", True),
    "claim": ("graph_node", "claim", True),
    "operator_note": ("user_authored", "operator_note", False),
}

# Placeholder for operator_note content — the old model never stored the
# text, only an id. We surface that honestly rather than inventing prose.
_OPERATOR_NOTE_PLACEHOLDER = "(migrated operator note — original text not in legacy store)"


@dataclass
class MigrationResult:
    """What a migration run did. ``migrated`` + ``skipped`` sum to the
    section_blocks row count; ``skipped`` is the idempotent no-op count."""

    migrated: int = 0
    skipped: int = 0
    unmapped: list[str] = field(default_factory=list)
    block_ids: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.migrated + self.skipped


def _assert_write_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"migration requires a LockedConnection (got {type(con).__name__}). "
            "Acquire via runtime.db_lock.connect_write(db_path, purpose=...)."
        )


def migrate(con: LockedConnection, *, investigation_id: str = "__operator__") -> MigrationResult:
    """Migrate all ``section_blocks`` rows into ``outline_blocks``.
    Idempotent and non-destructive. Returns a ``MigrationResult``."""
    _assert_write_locked(con)
    rows = con.execute(
        "SELECT sb.section_id, sb.block_kind, sb.block_id, sb.block_index "
        "FROM section_blocks sb "
        "ORDER BY sb.section_id, sb.block_index, sb.block_kind, sb.block_id"
    ).fetchall()

    result = MigrationResult()
    for section_id, block_kind, block_id, block_index in rows:
        mapping = _KIND_MAP.get(block_kind)
        if mapping is None:
            result.unmapped.append(f"{block_kind}:{block_id}")
            continue
        provenance_kind, new_kind, node_backed = mapping
        obid = content_addressed_id(
            "oblk", f"{section_id}|{block_kind}|{block_id}"
        )
        # Idempotency probe: count first so we can report migrated vs skipped.
        exists = con.execute(
            "SELECT 1 FROM outline_blocks WHERE outline_block_id = ? LIMIT 1",
            [obid],
        ).fetchone() is not None

        place_block(
            con,
            section_id=section_id,
            block_kind=new_kind,
            provenance_kind=provenance_kind,
            node_id=(block_id if node_backed else None),
            content=(None if node_backed else _OPERATOR_NOTE_PLACEHOLDER),
            source_block_kind=block_kind,
            source_block_id=block_id,
            block_index=int(block_index),
            outline_block_id=obid,
            investigation_id=investigation_id,
            metadata=(
                None if node_backed
                else {"migrated_from": "section_blocks", "original_block_id": block_id}
            ),
            on_conflict="ignore",
        )
        result.block_ids.append(obid)
        if exists:
            result.skipped += 1
        else:
            result.migrated += 1
    return result
