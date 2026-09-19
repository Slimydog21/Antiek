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
    notebook_id = prev_state.get("notebook_id")
    account_id = prev_state.get("account_id")
    if not isinstance(notebook_id, str) or not isinstance(account_id, str):
        raise ValueError("prev_state missing notebook authority")
    from substrate.notebooks import restore_block
    from substrate.notebooks.authority import NotebookAccountAuthority

    restore_block(
        con,
        NotebookAccountAuthority(account_id).notebook(notebook_id),
        block_id,
        block_index=int(prev_state.get("block_index", 0)),
        block_type=block_type,
        ref_id=ref_id,
        content=content,
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
    account_id = prev_state.get("account_id")
    if not isinstance(account_id, str):
        raise ValueError("prev_state missing notebook authority")
    from substrate.notebooks import restore_notebook_metadata
    from substrate.notebooks.authority import NotebookAccountAuthority

    restore_notebook_metadata(
        con,
        NotebookAccountAuthority(account_id).notebook(target_id),
        title=prev_state.get("title"),
        content_class=prev_state.get("content_class"),
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
