"""Takedown path — the cheap pre-serve defence (SPR-01 M4).

*Bartz v. Anthropic* (~$1.5B settlement) priced post-serve damages far
above the cost of pre-serve takedown. So takedown is fast, total, and
auditable. When a removal demand arrives for a book, :func:`take_down`:

1. Saves the book's current ``content_class`` to
   ``book_assets.pre_takedown_content_class`` (so the action is
   reversible).
2. Moves ``documents.content_class`` to the existing
   ``restricted_pending_opt_in`` gate (``TAKEDOWN_CONTENT_CLASS``). This
   is the keystone reuse: BOTH the full-text serve allowlist AND the
   chunk-search G1 denylist already exclude restricted content, so a
   taken-down book vanishes from every retrieval path without a new
   gating mechanism.
3. Purges the materialized full text by nulling ``documents.raw_text``
   (the "cached served full text" the spec requires gone).
4. Flips ``book_assets.taken_down = TRUE`` with a timestamp + reason.
5. Emits a ``book.taken_down`` audit event.

All five happen under one write lock so a takedown is atomic — there is
no window where the flag is set but the text is still servable.

Reinstatement (:func:`reinstate`) restores the saved content_class and
clears the flag, but does NOT restore ``raw_text`` — the body was purged
and must be re-ingested. Takedown is meant to be heavy to undo; that
asymmetry is the point.
"""

from __future__ import annotations

from typing import Any

from runtime.db_lock import LockedConnection
from substrate.constants import SYSTEM_INVESTIGATION_ID, TAKEDOWN_CONTENT_CLASS
from substrate.event_log import emit_typed
from substrate.graph.ops import update_document_gate_columns
from substrate.schemas.events import BookServabilityChangedPayload, BookTakenDownPayload

from .servability import ServabilityStatus, servability_of


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"takedown requires a LockedConnection (got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path)."
        )


class BookNotRegistered(RuntimeError):
    """Raised when a takedown/reinstate targets a document_id that has no
    ``book_assets`` row — you can only take down a registered book."""


def take_down(con: LockedConnection, document_id: str, *, reason: str) -> bool:
    """Take a book out of serving immediately and purge its cached full
    text. Idempotent: taking down an already-taken-down book is a no-op
    that returns ``False`` (no second purge, no duplicate event). Returns
    ``True`` when this call performed the takedown.
    """
    _require_locked(con)
    row = con.execute(
        """
        SELECT d.content_class, d.raw_text, COALESCE(b.taken_down, FALSE)
        FROM book_assets b
        JOIN documents d ON b.document_id = d.document_id
        WHERE b.document_id = ?
        """,
        [document_id],
    ).fetchone()
    if row is None:
        raise BookNotRegistered(
            f"{document_id} is not a registered book (no book_assets row)."
        )
    content_class, raw_text, already_down = row
    if bool(already_down):
        return False

    had_full_text = bool(raw_text)
    prev_status = servability_of(content_class, taken_down=False)

    # 2 + 3: restrict retrieval via the existing gate AND purge the body.
    # The gate primitive handles the DuckDB indexed-column-on-FK-target
    # limitation; raw_text rides the same UPDATE for atomicity.
    update_document_gate_columns(
        con,
        document_id,
        content_class=TAKEDOWN_CONTENT_CLASS,
        set_content_class=True,
        null_raw_text=True,
    )
    # 1 + 4: save the prior class (reversibility) and flip the flag.
    con.execute(
        """
        UPDATE book_assets
        SET taken_down = TRUE,
            taken_down_at = CURRENT_TIMESTAMP,
            takedown_reason = ?,
            pre_takedown_content_class = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE document_id = ?
        """,
        [reason, content_class, document_id],
    )

    # 5: audit. The document_id rides the envelope.
    emit_typed(
        SYSTEM_INVESTIGATION_ID,
        BookTakenDownPayload(
            reason=reason,
            previous_content_class=content_class,
            purged_full_text=had_full_text,
        ),
        document_id=document_id,
        role="read/books",
        policy_id="read/books/takedown",
    )
    # The servability transition is also a servability-changed event so a
    # single query over book.servability_changed reconstructs the full
    # serving-eligibility history.
    emit_typed(
        SYSTEM_INVESTIGATION_ID,
        BookServabilityChangedPayload(
            from_status=prev_status.value,
            to_status=ServabilityStatus.TAKEN_DOWN.value,
            reason=f"takedown: {reason}",
        ),
        document_id=document_id,
        role="read/books",
        policy_id="read/books/takedown",
    )
    return True


def reinstate(con: LockedConnection, document_id: str) -> bool:
    """Reverse a takedown: restore the saved content_class and clear the
    flag. Does NOT restore ``raw_text`` (purged on takedown — re-ingest to
    serve full text again). Returns ``True`` when a reinstatement happened,
    ``False`` if the book wasn't taken down.
    """
    _require_locked(con)
    row = con.execute(
        """
        SELECT COALESCE(b.taken_down, FALSE), b.pre_takedown_content_class
        FROM book_assets b WHERE b.document_id = ?
        """,
        [document_id],
    ).fetchone()
    if row is None:
        raise BookNotRegistered(
            f"{document_id} is not a registered book (no book_assets row)."
        )
    taken_down, pre_class = row
    if not bool(taken_down):
        return False

    update_document_gate_columns(
        con, document_id, content_class=pre_class, set_content_class=True,
    )
    con.execute(
        """
        UPDATE book_assets
        SET taken_down = FALSE, taken_down_at = NULL,
            takedown_reason = NULL, pre_takedown_content_class = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE document_id = ?
        """,
        [document_id],
    )
    emit_typed(
        SYSTEM_INVESTIGATION_ID,
        BookServabilityChangedPayload(
            from_status=ServabilityStatus.TAKEN_DOWN.value,
            to_status=servability_of(pre_class, taken_down=False).value,
            reason="reinstated after takedown (full text requires re-ingest)",
        ),
        document_id=document_id,
        role="read/books",
        policy_id="read/books/reinstate",
    )
    return True
