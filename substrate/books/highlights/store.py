"""Connection-taking persistence for anchored highlights (anchor-first SPR-01).

Row CRUD under LockedConnection, following the substrate/feedback/store.py
shape: commands are frozen dataclasses, every write goes through one method,
the idempotent schema is ensured on write entry points. The anchor payload
itself is the PROVEN NodeTextAnchor (substrate/feedback/domain.py) — this
module IMPORTS it, never forks it.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from enum import StrEnum

from runtime.db_lock import LockedConnection
from substrate.books.highlights.schema import SqlExecutor, init_highlights_schema
from substrate.feedback.domain import NodeTextAnchor


class HighlightSource(StrEnum):
    """Where the pin came from (the spec's closed vocabulary)."""

    FLOATMENU_NOTE = "floatmenu_note"
    FLOATMENU_DIALOGUE = "floatmenu_dialogue"
    FLOATMENU_SEARCH = "floatmenu_search"
    FLOATMENU_DEEP_RESEARCH = "floatmenu_deep_research"
    PIN = "pin"


class HighlightStatus(StrEnum):
    """The anchor lifecycle (the spec's re-resolution vocabulary)."""

    ACTIVE = "active"
    DRIFTED = "drifted"
    ORPHANED = "orphaned"


@dataclass(frozen=True, slots=True)
class AnchorRow:
    """One persisted anchored highlight."""

    anchor_id: str
    owner_user_id: str
    document_id: str
    anchor: NodeTextAnchor
    servable_at_pin: bool
    selection_text_sha256: str
    page_index_hint: int | None
    source: HighlightSource
    status: HighlightStatus
    investigation_id: str | None
    created_at: str
    updated_at: str

    def to_node_text_anchor(self) -> NodeTextAnchor:
        """The row's anchor as the proven dataclass. Only lawful for a
        servable pin (text columns present); a metadata-only anchor has no
        quote to rebuild — the caller checks servable_at_pin first."""
        return self.anchor

    def to_lease_payload(self) -> dict[str, object]:
        """The anchor dict in EXACTLY the lease payload's field set
        (interfaces/research/api/agent_work_routes.py:199-208) — the payload
        parity proof round-trips through this."""
        return {
            "normalization": self.anchor.normalization,
            "node_id": self.anchor.node_id,
            "node_text_sha256": self.anchor.node_text_sha256,
            "start_scalar": self.anchor.start_scalar,
            "end_scalar": self.anchor.end_scalar,
            "quote": self.anchor.quote,
            "prefix": self.anchor.prefix,
            "suffix": self.anchor.suffix,
        }


@dataclass(frozen=True, slots=True)
class CreatePinCommand:
    owner_user_id: str
    document_id: str
    anchor: NodeTextAnchor
    servable_at_pin: bool
    source: HighlightSource
    page_index_hint: int | None
    investigation_id: str | None = None
    anchor_id: str | None = None


def _mint_anchor_id() -> str:
    return f"ahl-{secrets.token_hex(8)}"


def selection_sha256(normalized_quote: str) -> str:
    """One-way hash of the selected text — lawful to store even for a
    metadata-only (withheld) pin, where the text itself is never persisted."""
    return hashlib.sha256(normalized_quote.encode("utf-8")).hexdigest()


class HighlightsStore:
    """Persist and read anchored highlights."""

    def create_pin(self, con: LockedConnection, command: CreatePinCommand) -> AnchorRow:
        init_highlights_schema(con)
        anchor = command.anchor
        if command.servable_at_pin:
            quote: str | None = anchor.quote
            prefix: str | None = anchor.prefix
            suffix: str | None = anchor.suffix
        else:
            # Rights truth at rest: a non-servable book's body never lands in
            # the row. The CHECK constraint is the DB-layer backstop.
            quote = prefix = suffix = None
        anchor_id = command.anchor_id or _mint_anchor_id()
        con.execute(
            "INSERT INTO anchored_highlights ("
            "anchor_id, owner_user_id, document_id, normalization, "
            "anchor_node_id, anchor_node_text_sha256, "
            "anchor_start_scalar, anchor_end_scalar, servable_at_pin, "
            "anchor_quote, anchor_prefix, anchor_suffix, "
            "selection_text_sha256, page_index_hint, source, status, "
            "investigation_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                anchor_id,
                command.owner_user_id,
                command.document_id,
                anchor.normalization,
                anchor.node_id,
                anchor.node_text_sha256,
                anchor.start_scalar,
                anchor.end_scalar,
                command.servable_at_pin,
                quote,
                prefix,
                suffix,
                selection_sha256(anchor.quote),
                command.page_index_hint,
                str(command.source),
                str(HighlightStatus.ACTIVE),
                command.investigation_id,
            ],
        )
        row = self.get(con, anchor_id)
        if row is None:  # pragma: no cover - database invariant
            raise RuntimeError("the pin just written could not be read back")
        return row

    def get(self, con: SqlExecutor, anchor_id: str) -> AnchorRow | None:
        # No init here: this is a READ path (a CREATE on a read connection
        # fails). Write entry points (create_pin / updates / delete) ensure
        # the schema; a read on a store without pins finds zero rows via the
        # router's highlights_table_exists guard.
        row = con.execute(
            "SELECT anchor_id, owner_user_id, document_id, normalization, "
            "anchor_node_id, anchor_node_text_sha256, anchor_start_scalar, "
            "anchor_end_scalar, servable_at_pin, anchor_quote, anchor_prefix, "
            "anchor_suffix, selection_text_sha256, page_index_hint, source, "
            "status, investigation_id, created_at, updated_at "
            "FROM anchored_highlights WHERE anchor_id = ?",
            [anchor_id],
        ).fetchone()
        if row is None:
            return None
        return _row_to_anchor(row)

    def list_for_document(self, con: SqlExecutor, document_id: str) -> list[AnchorRow]:
        # No init here — a READ path (see get()). The router guards a
        # never-pinned store with highlights_table_exists; write entry
        # points ensure the schema.
        rows = con.execute(
            "SELECT anchor_id, owner_user_id, document_id, normalization, "
            "anchor_node_id, anchor_node_text_sha256, anchor_start_scalar, "
            "anchor_end_scalar, servable_at_pin, anchor_quote, anchor_prefix, "
            "anchor_suffix, selection_text_sha256, page_index_hint, source, "
            "status, investigation_id, created_at, updated_at "
            "FROM anchored_highlights WHERE document_id = ? "
            "ORDER BY created_at, anchor_id",
            [document_id],
        ).fetchall()
        return [_row_to_anchor(r) for r in rows]

    def update_after_reanchor(
        self,
        con: LockedConnection,
        anchor_id: str,
        *,
        node_id: str,
        node_text_sha256: str,
        start_scalar: int,
        end_scalar: int,
        status: HighlightStatus,
        quote: str | None,
        prefix: str | None,
        suffix: str | None,
    ) -> None:
        """Rewrite an anchor's location+status after a re-resolution step.

        The re-resolution ladder is the only caller: migration rewrites the
        node id, drift rewrites offsets (+ the new location's context), and
        both rewrites keep the row's rights posture (text columns stay NULL
        for metadata-only anchors — the CHECK is the backstop)."""
        init_highlights_schema(con)
        con.execute(
            "UPDATE anchored_highlights SET "
            "anchor_node_id = ?, anchor_node_text_sha256 = ?, "
            "anchor_start_scalar = ?, anchor_end_scalar = ?, "
            "status = ?, anchor_quote = ?, anchor_prefix = ?, anchor_suffix = ?, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE anchor_id = ?",
            [
                node_id,
                node_text_sha256,
                start_scalar,
                end_scalar,
                str(status),
                quote,
                prefix,
                suffix,
                anchor_id,
            ],
        )

    def update_status(self, con: LockedConnection, anchor_id: str, status: HighlightStatus) -> None:
        init_highlights_schema(con)
        con.execute(
            "UPDATE anchored_highlights SET status = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE anchor_id = ?",
            [str(status), anchor_id],
        )

    def delete(self, con: LockedConnection, anchor_id: str, owner_user_id: str) -> bool:
        """The ONLY removal path — an explicit owner delete. Anything else
        (drift, orphan) keeps the row, per the never-silently-lost invariant."""
        init_highlights_schema(con)
        # Existence within the same scope is the deterministic affected-rows
        # answer (this DuckDB has no changes() and cursor rowcount is
        # unreliable for DML).
        prior = con.execute(
            "SELECT 1 FROM anchored_highlights WHERE anchor_id = ? AND owner_user_id = ?",
            [anchor_id, owner_user_id],
        ).fetchone()
        if prior is None:
            return False
        con.execute(
            "DELETE FROM anchored_highlights WHERE anchor_id = ? AND owner_user_id = ?",
            [anchor_id, owner_user_id],
        )
        return True


def _row_to_anchor(row: tuple[object, ...]) -> AnchorRow:
    servable = bool(row[8])
    return AnchorRow(
        anchor_id=str(row[0]),
        owner_user_id=str(row[1]),
        document_id=str(row[2]),
        anchor=NodeTextAnchor(
            normalization=str(row[3]),
            node_id=str(row[4]),
            node_text_sha256=str(row[5]),
            start_scalar=int(str(row[6])),
            end_scalar=int(str(row[7])),
            quote=str(row[9]) if servable and row[9] is not None else "",
            prefix=str(row[10]) if servable and row[10] is not None else "",
            suffix=str(row[11]) if servable and row[11] is not None else "",
        ),
        servable_at_pin=servable,
        selection_text_sha256=str(row[12]),
        page_index_hint=None if row[13] is None else int(str(row[13])),
        source=HighlightSource(str(row[14])),
        status=HighlightStatus(str(row[15])),
        investigation_id=None if row[16] is None else str(row[16]),
        created_at=str(row[17]),
        updated_at=str(row[18]),
    )
