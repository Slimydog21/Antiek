"""AI sidecar undoable actions (PostHog Wedge 4, master-spec §5.5).

Every AI-driven UI mutation routes through ``apply_ai_action`` which:

1. Writes the substrate change.
2. Emits ``ai.action.applied`` with prev_state + next_state.
3. Returns the event_id so the caller can later invert.

The undo path is ``undo_ai_action(event_id)``:

1. Looks up the ``ai.action.applied`` event.
2. Verifies the current substrate state matches ``next_state`` (else
   concurrent edit detected — refuse the undo).
3. Re-applies ``prev_state`` via the per-kind handler.
4. Emits ``ai.action.undone`` linking back via ``inverted_event_id``.

Per-kind handlers live in ``handlers.py`` and are registered into a
single dispatch table — one entry per ``target_kind`` (notebook_block,
master_md_section, etc.). The substrate write happens inside the same
``connect_write`` lock that emits the events so a partial state never
escapes.
"""

from substrate.ai_actions.actions import (
    AIActionError,
    apply_ai_action,
    undo_ai_action,
)
from substrate.ai_actions.handlers import (
    HANDLERS,
    InverseHandler,
    register_handler,
)

__all__ = [
    "AIActionError",
    "HANDLERS",
    "InverseHandler",
    "apply_ai_action",
    "register_handler",
    "undo_ai_action",
]
