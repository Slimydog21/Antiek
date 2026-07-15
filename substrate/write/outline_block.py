"""OutlineBlock — the Write composition primitive (specs/write/ SPR-01).

A lego block is a unit of meaning placed in an outline section. It either
references an insight/question/claim **graph node** (so it traces back to
a source document — the provenance moat) or is explicitly **user-
originated** (operator-authored, synthesized, or emerged in a brainstorm).
There is no third option: a block never carries a fabricated citation to
a source it did not come from.

This extends the existing Deliverable/Section/Block model:

    deliverables                      (operator-assembled document)
      └─ deliverable_sections         (hierarchy via parent_section_id)
           └─ outline_blocks          (THIS — the leaf composition units)

``outline_blocks`` SUPERSEDES the older ``section_blocks`` table as the
composition layer; ``section_blocks`` stays as the migration source (see
``migrate_outline_block.py``). The block model is a strict superset:

- ``block_kind`` extends — does not replace — the section_blocks
  vocabulary with two Write-native kinds:
    insight | open_question | operator_note | claim   (existing)
    user_authored | synthesized                       (Write-native)
- ``provenance_kind`` is the orthogonal *trace* discriminator —
  block_kind says **what** a block is; provenance_kind says **how it
  traces to truth**:
    graph_node     → node_id references a graph node; provenance resolves
                     node → document → chunks. content is null.
    user_authored  → the operator wrote it. node_id null; content set.
    synthesized    → produced by generation from other blocks. node_id null.
    brainstorm     → emerged in a brainstorm session (SPR-05);
                     user-originated, traces to the session, node_id null.

The no-orphan-prose invariant (``graph_node ⟺ node_id present``) is
enforced at THREE layers: this module (loud, typed errors), the typed
Pydantic payload (Literal validators), and the DB CHECK constraint
(``substrate/graph/schema.py`` V8). A maintainer can confirm there is no
path that produces a graph-provenance block without a node, nor a
user-originated block with a fabricated node reference.

Single-writer discipline: every write takes a ``LockedConnection`` from
``runtime/db_lock.connect_write`` and emits a typed event AFTER the row
commits (mirrors ``substrate/graph/ops.py``).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

try:
    from ...runtime.db_lock import LockedConnection
    from ..event_log import emit_typed
    from ..graph.ops import new_random_id
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.graph.ops import new_random_id  # type: ignore[no-redef]

from substrate.schemas.events import (
    OutlineBlockMovedPayload,
    OutlineBlockPlacedPayload,
    OutlineBlockRemovedPayload,
)

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

BlockKind = Literal[
    "insight", "open_question", "operator_note", "claim",
    "user_authored", "synthesized",
]
ProvenanceKind = Literal["graph_node", "user_authored", "synthesized", "brainstorm"]

BLOCK_KINDS: tuple[str, ...] = (
    "insight", "open_question", "operator_note", "claim",
    "user_authored", "synthesized",
)
PROVENANCE_KINDS: tuple[str, ...] = (
    "graph_node", "user_authored", "synthesized", "brainstorm",
)

# Provenance kinds that resolve to a graph node (and therefore require a
# node_id). The complement is "user-originated": no external source, so a
# node_id would be a fabricated citation.
_NODE_BACKED: frozenset[str] = frozenset({"graph_node"})

# Coherent (block_kind, provenance_kind) pairs. block_kind is descriptive;
# provenance_kind is load-bearing. The pairing rules keep the taxonomy
# legible and block nonsense (e.g. a 'claim' marked user_authored with no
# node — a fabricated-provenance risk). Brainstorm-originated insight /
# question blocks (SPR-05) are explicitly allowed: the user asserted them
# in a session, so they are user-originated (node_id null) but still typed
# as insight/open_question for the outline.
_COHERENT_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("insight", "graph_node"),
    ("open_question", "graph_node"),
    ("claim", "graph_node"),
    ("operator_note", "user_authored"),
    ("user_authored", "user_authored"),
    ("user_authored", "brainstorm"),
    ("synthesized", "synthesized"),
    ("insight", "brainstorm"),
    ("open_question", "brainstorm"),
})


class OutlineBlockError(ValueError):
    """Raised when an OutlineBlock would violate a composition invariant
    (the no-orphan-prose / no-fabricated-citation rules, or an incoherent
    block_kind / provenance_kind pairing)."""


# ---------------------------------------------------------------------------
# Read model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutlineBlock:
    """One lego block in an outline. Frozen — the read projection of an
    ``outline_blocks`` row."""

    outline_block_id: str
    section_id: str
    block_kind: str
    provenance_kind: str
    node_id: str | None
    source_block_kind: str | None
    source_block_id: str | None
    content: str | None
    block_index: int
    cluster_id: str | None
    created_at: str | None = None
    metadata: dict | None = None

    @property
    def is_user_originated(self) -> bool:
        """True when the block traces to the user/session rather than an
        external graph node. These never carry a node_id."""
        return self.provenance_kind != "graph_node"

    @property
    def display_text(self) -> str:
        """Best-effort text for surfaces: inline content for user-
        originated blocks, else empty (node-backed text is resolved from
        the node by provenance.py — not duplicated here)."""
        return self.content or ""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_composition(
    *,
    block_kind: str,
    provenance_kind: str,
    node_id: str | None,
    content: str | None,
) -> None:
    """Enforce the no-orphan-prose / no-fabricated-citation invariants
    before any write. Raises ``OutlineBlockError`` with a precise reason."""
    if block_kind not in BLOCK_KINDS:
        raise OutlineBlockError(
            f"unknown block_kind {block_kind!r}; expected one of {BLOCK_KINDS}"
        )
    if provenance_kind not in PROVENANCE_KINDS:
        raise OutlineBlockError(
            f"unknown provenance_kind {provenance_kind!r}; expected one of "
            f"{PROVENANCE_KINDS}"
        )
    if (block_kind, provenance_kind) not in _COHERENT_PAIRS:
        raise OutlineBlockError(
            f"incoherent (block_kind, provenance_kind) pair "
            f"({block_kind!r}, {provenance_kind!r}). Allowed pairs keep the "
            "taxonomy legible and prevent fabricated provenance. See "
            "_COHERENT_PAIRS in substrate/write/outline_block.py."
        )
    if provenance_kind in _NODE_BACKED:
        if not node_id:
            raise OutlineBlockError(
                f"provenance_kind={provenance_kind!r} requires a node_id "
                "(a block claiming graph provenance must name its source "
                "node). This is the no-orphan-prose invariant."
            )
        if content is not None:
            raise OutlineBlockError(
                "a node-backed block must not carry inline content — the "
                "node is the content of record (resolve it via "
                "provenance.py). Pass content=None for graph_node blocks."
            )
    else:
        # User-originated: a node_id would be a fabricated citation.
        if node_id is not None:
            raise OutlineBlockError(
                f"provenance_kind={provenance_kind!r} is user-originated and "
                "must NOT carry a node_id — attaching one fabricates a "
                "citation to a source the block did not come from."
            )
        if not content or not content.strip():
            raise OutlineBlockError(
                f"provenance_kind={provenance_kind!r} requires non-empty "
                "content (the user-originated text). It has no node to "
                "resolve text from."
            )


def _assert_write_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"outline_block writes require a LockedConnection (got "
            f"{type(con).__name__}). Acquire via "
            "runtime.db_lock.connect_write(db_path, purpose=...). "
            "Architecture_notes §2.3: the only-writer invariant."
        )


def _maybe_json(obj: Any | None) -> str | None:
    if obj is None:
        return None
    if isinstance(obj, str):
        json.loads(obj)  # validate
        return obj
    return json.dumps(obj, default=str)


def _resolve_deliverable_id(con: Any, section_id: str) -> str:
    row = con.execute(
        "SELECT deliverable_id FROM deliverable_sections WHERE section_id = ?",
        [section_id],
    ).fetchone()
    if row is None:
        raise OutlineBlockError(f"section not found: {section_id!r}")
    return row[0]


# ---------------------------------------------------------------------------
# Write ops
# ---------------------------------------------------------------------------


def _normalize_section_indices(con: LockedConnection, section_id: str) -> None:
    """Repair legacy sparse/duplicate ordering before applying a final seam."""
    rows = con.execute(
        "SELECT outline_block_id FROM outline_blocks WHERE section_id = ? "
        "ORDER BY block_index, outline_block_id",
        [section_id],
    ).fetchall()
    for index, (block_id,) in enumerate(rows):
        con.execute(
            "UPDATE outline_blocks SET block_index = ? WHERE outline_block_id = ?",
            [index, block_id],
        )


def place_block(
    con: LockedConnection,
    *,
    section_id: str,
    block_kind: str,
    provenance_kind: str,
    block_index: int,
    node_id: str | None = None,
    content: str | None = None,
    source_block_kind: str | None = None,
    source_block_id: str | None = None,
    cluster_id: str | None = None,
    metadata: Any | None = None,
    deliverable_id: str | None = None,
    investigation_id: str = "__operator__",
    outline_block_id: str | None = None,
    parent_event_id: str | None = None,
    on_conflict: Literal["error", "ignore"] = "error",
    emit_event: bool = True,
) -> str:
    """Place a lego block into an outline section. Returns its
    ``outline_block_id`` and normally emits ``OUTLINE_BLOCK_PLACED``.

    The composition invariants are validated *before* the write (loud,
    typed). ``on_conflict='ignore'`` makes the write idempotent for a
    caller-supplied ``outline_block_id`` (used by the migration).
    Transactional bulk callers must pass ``emit_event=False`` and provide a
    durable lineage mechanism; JSONL cannot commit atomically with DuckDB."""
    _assert_write_locked(con)
    _validate_composition(
        block_kind=block_kind, provenance_kind=provenance_kind,
        node_id=node_id, content=content,
    )
    obid = outline_block_id or new_random_id("oblk")
    if on_conflict == "ignore":
        exists = con.execute(
            "SELECT 1 FROM outline_blocks WHERE outline_block_id = ? LIMIT 1",
            [obid],
        ).fetchone()
        if exists is not None:
            return obid  # idempotent: no INSERT, no event
    did = deliverable_id or _resolve_deliverable_id(con, section_id)
    # ``block_index`` names a final visual seam. Make room before inserting so
    # two blocks can never occupy the same position.
    _normalize_section_indices(con, section_id)
    existing_count = int(con.execute(
        "SELECT COUNT(*) FROM outline_blocks WHERE section_id = ?", [section_id]
    ).fetchone()[0])
    final_index = min(max(int(block_index), 0), existing_count)
    con.execute(
        "UPDATE outline_blocks SET block_index = block_index + 1 "
        "WHERE section_id = ? AND block_index >= ?",
        [section_id, final_index],
    )
    con.execute(
        "INSERT INTO outline_blocks "
        "(outline_block_id, section_id, block_kind, provenance_kind, "
        " node_id, source_block_kind, source_block_id, content, "
        " block_index, cluster_id, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            obid, section_id, block_kind, provenance_kind, node_id,
            source_block_kind, source_block_id, content, final_index,
            cluster_id, _maybe_json(metadata),
        ],
    )
    if emit_event:
        emit_typed(
            investigation_id,
            OutlineBlockPlacedPayload(
                outline_block_id=obid,
                deliverable_id=did,
                section_id=section_id,
                block_kind=block_kind,  # type: ignore[arg-type]
                provenance_kind=provenance_kind,  # type: ignore[arg-type]
                node_id=node_id,
                block_index=final_index,
            ),
            parent_event_id=parent_event_id,
            role="write_composition",
        )
    return obid


def place_node_block(
    con: LockedConnection,
    *,
    section_id: str,
    node_id: str,
    block_kind: Literal["insight", "open_question", "claim"],
    block_index: int,
    provenance_kind: Literal["graph_node", "brainstorm"] = "graph_node",
    **kwargs: Any,
) -> str:
    """Convenience: place a graph-node-backed block (the dominant case —
    dragging an insight/question/claim from research into the outline)."""
    return place_block(
        con, section_id=section_id, block_kind=block_kind,
        provenance_kind=provenance_kind,
        node_id=(node_id if provenance_kind == "graph_node" else None),
        content=(None if provenance_kind == "graph_node" else kwargs.pop("content", "")),
        block_index=block_index, **kwargs,
    )


def place_user_authored_block(
    con: LockedConnection,
    *,
    section_id: str,
    content: str,
    block_index: int,
    block_kind: Literal["operator_note", "user_authored"] = "user_authored",
    provenance_kind: Literal["user_authored", "brainstorm"] = "user_authored",
    **kwargs: Any,
) -> str:
    """Convenience: place a user-originated block (operator wrote it, or
    it emerged in a brainstorm). Never carries a node_id — no fabricated
    citation."""
    return place_block(
        con, section_id=section_id, block_kind=block_kind,
        provenance_kind=provenance_kind, content=content,
        block_index=block_index, **kwargs,
    )


def move_block(
    con: LockedConnection,
    *,
    outline_block_id: str,
    to_section_id: str,
    to_index: int,
    investigation_id: str = "__operator__",
    parent_event_id: str | None = None,
) -> None:
    """Reorder a block within its section, or move it to another section
    (reparent). Emits ``OUTLINE_BLOCK_MOVED`` with both endpoints."""
    _assert_write_locked(con)
    row = con.execute(
        "SELECT section_id, block_index FROM outline_blocks "
        "WHERE outline_block_id = ?",
        [outline_block_id],
    ).fetchone()
    if row is None:
        raise OutlineBlockError(f"outline block not found: {outline_block_id!r}")
    from_section_id, from_index = row[0], int(row[1])
    # Validate the target section exists (reparent target).
    if to_section_id != from_section_id:
        if con.execute(
            "SELECT 1 FROM deliverable_sections WHERE section_id = ?",
            [to_section_id],
        ).fetchone() is None:
            raise OutlineBlockError(f"target section not found: {to_section_id!r}")
    # Rebuild the affected order(s). The requested index is the block's FINAL
    # position after removal, which keeps same- and cross-section moves dense.
    def _ordered_ids(section_id: str, *, exclude: str | None = None) -> list[str]:
        rows = con.execute(
            "SELECT outline_block_id FROM outline_blocks WHERE section_id = ? "
            "ORDER BY block_index, outline_block_id",
            [section_id],
        ).fetchall()
        return [r[0] for r in rows if r[0] != exclude]

    source_ids = _ordered_ids(from_section_id, exclude=outline_block_id)
    target_ids = source_ids if to_section_id == from_section_id else _ordered_ids(to_section_id)
    final_index = min(max(int(to_index), 0), len(target_ids))
    target_ids.insert(final_index, outline_block_id)

    if to_section_id != from_section_id:
        for index, block_id in enumerate(source_ids):
            con.execute(
                "UPDATE outline_blocks SET block_index = ? WHERE outline_block_id = ?",
                [index, block_id],
            )
    for index, block_id in enumerate(target_ids):
        con.execute(
            "UPDATE outline_blocks SET section_id = ?, block_index = ? "
            "WHERE outline_block_id = ?",
            [to_section_id, index, block_id],
        )
    emit_typed(
        investigation_id,
        OutlineBlockMovedPayload(
            outline_block_id=outline_block_id,
            from_section_id=from_section_id,
            to_section_id=to_section_id,
            from_index=from_index,
            to_index=final_index,
        ),
        parent_event_id=parent_event_id,
        role="write_composition",
    )


def remove_block(
    con: LockedConnection,
    *,
    outline_block_id: str,
    investigation_id: str = "__operator__",
    parent_event_id: str | None = None,
) -> bool:
    """Remove a block from an outline. Returns True if a row was removed.
    The underlying graph node is untouched — removal is a composition
    edit, not a graph deletion. Emits ``OUTLINE_BLOCK_REMOVED``."""
    _assert_write_locked(con)
    row = con.execute(
        "SELECT section_id, block_index FROM outline_blocks WHERE outline_block_id = ?",
        [outline_block_id],
    ).fetchone()
    if row is None:
        return False
    section_id = row[0]
    _normalize_section_indices(con, section_id)
    removed_index = int(con.execute(
        "SELECT block_index FROM outline_blocks WHERE outline_block_id = ?",
        [outline_block_id],
    ).fetchone()[0])
    con.execute(
        "DELETE FROM outline_blocks WHERE outline_block_id = ?",
        [outline_block_id],
    )
    con.execute(
        "UPDATE outline_blocks SET block_index = block_index - 1 "
        "WHERE section_id = ? AND block_index > ?",
        [section_id, removed_index],
    )
    emit_typed(
        investigation_id,
        OutlineBlockRemovedPayload(
            outline_block_id=outline_block_id, section_id=section_id,
        ),
        parent_event_id=parent_event_id,
        role="write_composition",
    )
    return True


# ---------------------------------------------------------------------------
# Read ops
# ---------------------------------------------------------------------------


def _row_to_block(r: Iterable[Any]) -> OutlineBlock:
    r = list(r)
    meta = json.loads(r[10]) if r[10] else None
    return OutlineBlock(
        outline_block_id=r[0], section_id=r[1], block_kind=r[2],
        provenance_kind=r[3], node_id=r[4], source_block_kind=r[5],
        source_block_id=r[6], content=r[7], block_index=int(r[8]),
        cluster_id=r[9], metadata=meta,
        created_at=str(r[11]) if len(r) > 11 and r[11] is not None else None,
    )


_SELECT_COLS = (
    "outline_block_id, section_id, block_kind, provenance_kind, node_id, "
    "source_block_kind, source_block_id, content, block_index, cluster_id, "
    "metadata, created_at"
)


def list_section_blocks(con: Any, section_id: str) -> list[OutlineBlock]:
    """All blocks in a section, ordered by block_index (deterministic).
    Accepts any duckdb connection (read-only is fine)."""
    rows = con.execute(
        f"SELECT {_SELECT_COLS} FROM outline_blocks "
        "WHERE section_id = ? ORDER BY block_index, outline_block_id",
        [section_id],
    ).fetchall()
    return [_row_to_block(r) for r in rows]


def get_block(con: Any, outline_block_id: str) -> OutlineBlock | None:
    """Fetch one block by id, or None."""
    row = con.execute(
        f"SELECT {_SELECT_COLS} FROM outline_blocks WHERE outline_block_id = ?",
        [outline_block_id],
    ).fetchone()
    return _row_to_block(row) if row is not None else None
