"""Outline hierarchy over deliverable_sections (specs/write/ SPR-01 M2).

The ``deliverable_sections`` table has always carried a
``parent_section_id`` column, but it was dormant — sections rendered
flat. This module activates it: an outline is a tree

    deliverable
      └─ section (chapter)
           └─ section (section)
                └─ section (subsection)
                     └─ outline_blocks (leaves)

``build_outline_tree`` reconstructs the tree deterministically (ordered
by ``section_index`` then ``section_id``); ``reparent_section`` moves a
subtree with **cycle detection** (a section can never become its own
ancestor) and ``reorder_section`` bumps ordering. Flat (single-level)
outlines are the trivial case — every existing deliverable maps to a
depth-1 tree with no migration (see ``migrate_outline_block.py`` for the
block-level migration).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    from ...runtime.db_lock import LockedConnection
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]

from .outline_block import OutlineBlock, list_section_blocks


class OutlineError(ValueError):
    """Raised on an illegal outline mutation (e.g. a reparent that would
    create a cycle)."""


@dataclass
class OutlineNode:
    """One section in the outline tree, with its blocks and children."""

    section_id: str
    title: str | None
    section_index: int
    parent_section_id: str | None
    depth: int
    blocks: list[OutlineBlock] = field(default_factory=list)
    children: list[OutlineNode] = field(default_factory=list)


def _assert_write_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"outline writes require a LockedConnection (got {type(con).__name__}). "
            "Acquire via runtime.db_lock.connect_write(db_path, purpose=...)."
        )


def build_outline_tree(con: Any, deliverable_id: str) -> list[OutlineNode]:
    """Reconstruct the outline tree for a deliverable. Returns the root
    nodes ordered by ``(section_index, section_id)``; each node carries
    its blocks (ordered) and children (ordered). Deterministic.

    Orphan sections — a ``parent_section_id`` that points at a section
    outside this deliverable or at a now-deleted section — are surfaced at
    the root level rather than dropped, so structure is never silently
    lost. ``con`` may be any duckdb connection (read-only is fine)."""
    rows = con.execute(
        "SELECT section_id, parent_section_id, section_index, title "
        "FROM deliverable_sections WHERE deliverable_id = ? "
        "ORDER BY section_index, section_id",
        [deliverable_id],
    ).fetchall()

    nodes: dict[str, OutlineNode] = {}
    order: list[str] = []
    for r in rows:
        sid = r[0]
        nodes[sid] = OutlineNode(
            section_id=sid, parent_section_id=r[1],
            section_index=int(r[2]), title=r[3], depth=0,
        )
        order.append(sid)

    roots: list[OutlineNode] = []
    for sid in order:
        node = nodes[sid]
        parent_id = node.parent_section_id
        if parent_id and parent_id in nodes:
            nodes[parent_id].children.append(node)
        else:
            # No parent, or parent outside this deliverable → root-level.
            roots.append(node)

    # Assign depth via BFS and attach blocks per section.
    def _assign(node: OutlineNode, depth: int) -> None:
        node.depth = depth
        node.blocks = list_section_blocks(con, node.section_id)
        node.children.sort(key=lambda c: (c.section_index, c.section_id))
        for child in node.children:
            _assign(child, depth + 1)

    roots.sort(key=lambda n: (n.section_index, n.section_id))
    for root in roots:
        _assign(root, 0)
    return roots


def _descendants(con: Any, section_id: str) -> set[str]:
    """All transitive descendant section_ids of ``section_id`` (excluding
    itself). Used by the cycle check."""
    out: set[str] = set()
    frontier = [section_id]
    while frontier:
        current = frontier.pop()
        child_rows = con.execute(
            "SELECT section_id FROM deliverable_sections WHERE parent_section_id = ?",
            [current],
        ).fetchall()
        for cr in child_rows:
            if cr[0] not in out:
                out.add(cr[0])
                frontier.append(cr[0])
    return out


def reparent_section(
    con: LockedConnection,
    *,
    section_id: str,
    new_parent_section_id: str | None,
    new_index: int | None = None,
) -> None:
    """Move ``section_id`` under ``new_parent_section_id`` (or to the root
    if None). Refuses to create a cycle (a section cannot become its own
    descendant's parent). Optionally updates ``section_index``."""
    _assert_write_locked(con)
    cur = con.execute(
        "SELECT deliverable_id FROM deliverable_sections WHERE section_id = ?",
        [section_id],
    ).fetchone()
    if cur is None:
        raise OutlineError(f"section not found: {section_id!r}")

    if new_parent_section_id is not None:
        if new_parent_section_id == section_id:
            raise OutlineError("a section cannot be its own parent")
        parent_row = con.execute(
            "SELECT 1 FROM deliverable_sections WHERE section_id = ?",
            [new_parent_section_id],
        ).fetchone()
        if parent_row is None:
            raise OutlineError(f"new parent section not found: {new_parent_section_id!r}")
        if new_parent_section_id in _descendants(con, section_id):
            raise OutlineError(
                f"reparenting {section_id!r} under {new_parent_section_id!r} "
                "would create a cycle (the target is a descendant)."
            )

    if new_index is None:
        con.execute(
            "UPDATE deliverable_sections SET parent_section_id = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE section_id = ?",
            [new_parent_section_id, section_id],
        )
    else:
        con.execute(
            "UPDATE deliverable_sections SET parent_section_id = ?, "
            "section_index = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE section_id = ?",
            [new_parent_section_id, int(new_index), section_id],
        )


def reorder_section(
    con: LockedConnection, *, section_id: str, new_index: int,
) -> None:
    """Change a section's ordering position within its parent."""
    _assert_write_locked(con)
    con.execute(
        "UPDATE deliverable_sections SET section_index = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE section_id = ?",
        [int(new_index), section_id],
    )


def flatten_outline(roots: list[OutlineNode]) -> list[OutlineNode]:
    """Depth-first flatten of an outline tree (preorder). Useful for
    generation (SPR-06) which walks sections top-to-bottom."""
    out: list[OutlineNode] = []

    def _walk(node: OutlineNode) -> None:
        out.append(node)
        for child in node.children:
            _walk(child)

    for root in roots:
        _walk(root)
    return out
