"""Per-kind inverse handlers for AI-applied UI actions.

Each registered handler knows how to re-apply ``prev_state`` to a
single ``target_kind`` (notebook_block, master_md_section, etc.). The
``apply_ai_action`` + ``undo_ai_action`` paths in ``actions.py``
dispatch through the ``HANDLERS`` table.

A handler is a callable:

    def handler(con, *, target_id: str, prev_state: dict, next_state: dict) -> None

It runs inside the caller's ``connect_write`` lock, so it must NOT
open its own connection. It must restore the substrate to
``prev_state`` from whatever the current state is — typically the
"current state" equals ``next_state`` (no concurrent edit) but the
handler should be tolerant of intermediate concurrent writes that
the optimistic-concurrency check in ``actions.py`` already rejected.
"""

from __future__ import annotations

import json
from typing import Any, Protocol


class InverseHandler(Protocol):
    """Restore a single target to ``prev_state``."""

    def __call__(
        self,
        con: Any,
        *,
        target_id: str,
        prev_state: dict,
        next_state: dict,
    ) -> None:
        ...


HANDLERS: dict[str, InverseHandler] = {}


def register_handler(target_kind: str, handler: InverseHandler) -> None:
    """Register an inverse handler for ``target_kind``. Overwrites any
    existing registration for the same kind."""
    HANDLERS[target_kind] = handler


# ── Built-in handlers ────────────────────────────────────────────────


def _notebook_block_handler(
    con: Any,
    *,
    target_id: str,
    prev_state: dict,
    next_state: dict,
) -> None:
    """Restore a notebook_block row's content_json to ``prev_state``.

    ``prev_state`` carries the full pre-AI row shape: ``{block_id,
    notebook_id, block_index, block_type, ref_id, content_json}``.
    """
    block_id = target_id
    expected_block_id = prev_state.get("block_id")
    if expected_block_id and expected_block_id != block_id:
        raise ValueError(
            f"prev_state block_id mismatch: {expected_block_id} vs {block_id}"
        )
    # Restore the row. We update only the columns the AI could have
    # touched — block_type, ref_id, content_json. Index + notebook
    # binding are immutable from the AI's perspective.
    block_type = prev_state.get("block_type") or "prose"
    ref_id = prev_state.get("ref_id")
    content = prev_state.get("content_json") or {}
    if not isinstance(content, (dict, list)):
        content = {}
    content_json_str = json.dumps(content)

    row = con.execute(
        "SELECT 1 FROM notebook_blocks WHERE block_id = ?",
        [block_id],
    ).fetchone()
    if row is None:
        # The block was deleted in the AI action — re-insert it. The
        # block_index is whatever was last recorded; if a later
        # operator action shifted indexes, this re-insert may collide
        # at the OS level on the PK, but block_id is unique so the
        # PK is intact. We accept that the order may differ from the
        # pre-AI state when concurrent shifts happened.
        notebook_id = prev_state.get("notebook_id")
        block_index = prev_state.get("block_index", 0)
        if not notebook_id:
            raise ValueError("prev_state missing notebook_id for re-insert")
        con.execute(
            """
            INSERT INTO notebook_blocks (
                block_id, notebook_id, block_index, block_type, ref_id, content_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [block_id, notebook_id, block_index, block_type, ref_id, content_json_str],
        )
    else:
        con.execute(
            """
            UPDATE notebook_blocks
            SET block_type = ?, ref_id = ?, content_json = ?
            WHERE block_id = ?
            """,
            [block_type, ref_id, content_json_str, block_id],
        )


def _notebook_handler(
    con: Any,
    *,
    target_id: str,
    prev_state: dict,
    next_state: dict,
) -> None:
    """Restore a notebook row's metadata (title, content_class).

    Block content is owned by ``_notebook_block_handler`` — this only
    flips the notebook-level fields the AI could have changed.
    """
    title = prev_state.get("title")
    content_class = prev_state.get("content_class")
    if title is not None:
        con.execute(
            "UPDATE notebooks SET title = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE notebook_id = ?",
            [title, target_id],
        )
    if content_class is not None:
        con.execute(
            "UPDATE notebooks SET content_class = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE notebook_id = ?",
            [content_class, target_id],
        )


def _ui_layout_handler(
    con: Any,
    *,
    target_id: str,
    prev_state: dict,
    next_state: dict,
) -> None:
    """No-op substrate-side: UI layout state lives in the client's
    workspace store, not the substrate. The undo event is still
    recorded for audit; the client is responsible for restoring its
    own layout via the prev_state payload.

    This handler exists so the dispatcher in ``actions.py`` doesn't
    reject ``ui_layout`` as unknown; without it, layout undos would
    have no audit trail.
    """
    _ = con, target_id, prev_state, next_state


register_handler("notebook_block", _notebook_block_handler)
register_handler("notebook", _notebook_handler)
register_handler("ui_layout", _ui_layout_handler)
