"""Per-document notebook persistence (SPR-08 M6).

JSON-now / .antiek-later abstraction. The contract:

- ``NotebookPersistence`` is the protocol any backend MUST implement.
- ``JSONPersistence`` is the SPR-08 concrete implementation: writes
  the TipTap document JSON into ``notebook_documents.content_json``
  plus a normalised row per block into ``notebook_blocks``.
- SPR-09 swaps the writer for a ``.antiek``-native one (a structured
  binary container per master-spec §13.7). The SURFACE
  (``apps/reading/src/modes/Notebook/PerDocNotebook.tsx``) does not
  change; only the implementation class swapped in by ``get_default_persistence``.

Why a protocol and not a direct function call?
----------------------------------------------
The original Sprint 18 notebook surface (still live at
``apps/reading/src/modes/Notebook/index.tsx``) calls the API directly
with no intermediate. That worked when JSON-in-DuckDB was the only
target. SPR-09's ``.antiek`` swap will introduce a binary on-disk
format whose persistence call surface differs (read/write returns
bytes + a sidecar index). The protocol lets SPR-09 replace
``JSONPersistence`` with an ``AntiekPersistence`` whose constructor
takes the on-disk path and whose ``save_notebook`` writes the
container. The surface keeps its single ``persistence.save_notebook``
call.

Single-writer invariant
-----------------------
Every write goes through ``runtime.db_lock.connect_write``. The
read-side opens a non-read-only connection (DuckDB cannot mix
read-only and writer connections in one process; same pattern as
``substrate.behavior.consent._connect_for_read``).
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

import duckdb

try:
    from runtime.db_lock import connect_write
    from .blocks import BLOCK_TAXONOMY_VERSION, BLOCK_TYPES, BlockType
    from .schema import default_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from services.notebooks.blocks import (  # type: ignore[no-redef]
        BLOCK_TAXONOMY_VERSION,
        BLOCK_TYPES,
        BlockType,
    )
    from services.notebooks.schema import default_db_path  # type: ignore[no-redef]


# ── Identifier minting ──


def new_notebook_id() -> str:
    """``nbk-<12hex>-<ms epoch>`` — matches substrate.behavior.api
    convention for grep ergonomics across the polyglot seam."""
    return f"nbk-{uuid.uuid4().hex[:12]}-{int(time.time() * 1000)}"


def new_block_id() -> str:
    """``blk-<12hex>-<ms epoch>``."""
    return f"blk-{uuid.uuid4().hex[:12]}-{int(time.time() * 1000)}"


# ── Records ──


@dataclass
class BlockRecord:
    """One row out of ``notebook_blocks``. Mutable on purpose — the
    auto-populator builds these incrementally before writing."""

    block_id: str
    notebook_id: str
    block_type: str
    source_event_ids: list[str]
    content_json: dict[str, Any]
    position: float
    demoted_at: Optional[datetime] = None
    edited_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    document_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.block_type not in BLOCK_TYPES:
            raise ValueError(
                f"BlockRecord: unknown block_type {self.block_type!r}; "
                f"valid: {list(BLOCK_TYPES)}"
            )
        if not self.source_event_ids and self.block_type != BlockType.PROSE.value:
            # The "no + new block" invariant: every non-prose block
            # must trace to at least one Tier-1 event.
            raise ValueError(
                f"BlockRecord: block_type={self.block_type!r} requires "
                "at least one source_event_id. The no-authoring rule "
                "in BLOCK_TAXONOMY.md forbids substrate-detached blocks."
            )


@dataclass
class NotebookRecord:
    """One row out of ``notebook_documents`` plus its ordered blocks."""

    notebook_id: str
    user_id: str
    document_id: str
    title: Optional[str]
    content_json: dict[str, Any]
    format_version: int
    created_at: Optional[datetime]
    last_saved_at: Optional[datetime]
    blocks: list[BlockRecord] = field(default_factory=list)


# ── Save kinds ──

SAVE_KIND_AUTO = "auto"          # debounced (2s after last edit)
SAVE_KIND_EXPLICIT = "explicit"  # Cmd+S
SAVE_KIND_AUTO_POPULATE = "auto_populate"  # auto-populator commit

VALID_SAVE_KINDS: frozenset[str] = frozenset(
    {SAVE_KIND_AUTO, SAVE_KIND_EXPLICIT, SAVE_KIND_AUTO_POPULATE}
)


# ── Persistence protocol ──


class NotebookPersistence(Protocol):
    """The single abstraction SPR-09's .antiek swap replaces.

    Methods return primitive Python types (or ``NotebookRecord``) so
    the FastAPI layer can serialise them directly.
    """

    def get_or_create_notebook(
        self, *, user_id: str, document_id: str
    ) -> NotebookRecord: ...

    def load_notebook(
        self, *, user_id: str, document_id: str
    ) -> Optional[NotebookRecord]: ...

    def save_notebook(
        self,
        record: NotebookRecord,
        *,
        save_kind: str = SAVE_KIND_AUTO,
    ) -> NotebookRecord: ...

    def upsert_blocks(
        self,
        notebook_id: str,
        blocks: list[BlockRecord],
    ) -> list[BlockRecord]: ...

    def demote_block(
        self,
        block_id: str,
        *,
        demoted: bool = True,
    ) -> BlockRecord: ...


# ── JSON-DuckDB implementation ──


def _connect_for_read(db_path: str) -> "duckdb.DuckDBPyConnection":
    """Non-read-only connection used for SELECT-only paths. See
    ``substrate.behavior.consent._connect_for_read`` for the rationale."""
    return duckdb.connect(db_path)


def _ensure_utc(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return None


def _row_to_notebook(
    row: tuple[Any, ...], blocks: list[BlockRecord]
) -> NotebookRecord:
    return NotebookRecord(
        notebook_id=row[0],
        user_id=row[1],
        document_id=row[2],
        title=row[3],
        content_json=json.loads(row[4]) if isinstance(row[4], str) else (row[4] or {}),
        format_version=int(row[5]),
        created_at=_ensure_utc(row[6]),
        last_saved_at=_ensure_utc(row[7]),
        blocks=blocks,
    )


def _row_to_block(row: tuple[Any, ...]) -> BlockRecord:
    source_ids = row[3]
    if isinstance(source_ids, str):
        source_ids = json.loads(source_ids)
    content = row[5]
    if isinstance(content, str):
        content = json.loads(content)
    return BlockRecord(
        block_id=row[0],
        notebook_id=row[1],
        block_type=row[2],
        source_event_ids=list(source_ids or []),
        document_id=row[4],
        content_json=content or {},
        position=float(row[6]),
        demoted_at=_ensure_utc(row[7]),
        edited_at=_ensure_utc(row[8]),
        created_at=_ensure_utc(row[9]),
    )


_BLOCK_COLUMNS = (
    "block_id",
    "notebook_id",
    "block_type",
    "source_event_ids",
    "document_id",
    "content_json",
    "position",
    "demoted_at",
    "edited_at",
    "created_at",
)


class JSONPersistence:
    """SPR-08 persistence: JSON-into-DuckDB.

    SPR-09's swap point: replace this class with ``AntiekPersistence``
    whose ``save_notebook`` writes a ``.antiek`` container at
    ``~/.antiek/notebooks/<notebook_id>.antiek`` instead of into
    ``notebook_documents.content_json``. The surface
    (``PerDocNotebook.tsx``) does not change.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or default_db_path()

    @property
    def db_path(self) -> str:
        return self._db_path

    # ── Notebook lifecycle ──

    def get_or_create_notebook(
        self, *, user_id: str, document_id: str
    ) -> NotebookRecord:
        existing = self.load_notebook(user_id=user_id, document_id=document_id)
        if existing is not None:
            return existing

        notebook_id = new_notebook_id()
        con = connect_write(self._db_path, purpose="notebooks_create")
        try:
            con.execute(
                "INSERT INTO notebook_documents "
                "(notebook_id, user_id, document_id, title, content_json, "
                " format_version) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    notebook_id,
                    user_id,
                    document_id,
                    None,
                    json.dumps({}),
                    BLOCK_TAXONOMY_VERSION,
                ],
            )
        finally:
            con.close()
        loaded = self.load_notebook(user_id=user_id, document_id=document_id)
        # The race window for two concurrent get_or_create calls is closed
        # by the UNIQUE (user_id, document_id) constraint; either INSERT
        # wins, the other raises IntegrityError, and the second caller
        # falls through to load_notebook(). For SPR-08 single-user the
        # race is theoretical; the comment exists for SPR-22 multi-user.
        assert loaded is not None, "get_or_create_notebook: insert failed"
        return loaded

    def load_notebook(
        self, *, user_id: str, document_id: str
    ) -> Optional[NotebookRecord]:
        con = _connect_for_read(self._db_path)
        try:
            row = con.execute(
                "SELECT notebook_id, user_id, document_id, title, "
                "       content_json, format_version, created_at, "
                "       last_saved_at "
                "FROM notebook_documents "
                "WHERE user_id = ? AND document_id = ?",
                [user_id, document_id],
            ).fetchone()
            if row is None:
                return None
            blocks_rows = con.execute(
                f"SELECT {', '.join(_BLOCK_COLUMNS)} "
                f"FROM notebook_blocks "
                f"WHERE notebook_id = ? "
                f"ORDER BY position, created_at",
                [row[0]],
            ).fetchall()
        finally:
            con.close()
        blocks = [_row_to_block(b) for b in blocks_rows]
        return _row_to_notebook(row, blocks)

    def load_notebook_by_id(self, notebook_id: str) -> Optional[NotebookRecord]:
        con = _connect_for_read(self._db_path)
        try:
            row = con.execute(
                "SELECT notebook_id, user_id, document_id, title, "
                "       content_json, format_version, created_at, "
                "       last_saved_at "
                "FROM notebook_documents WHERE notebook_id = ?",
                [notebook_id],
            ).fetchone()
            if row is None:
                return None
            blocks_rows = con.execute(
                f"SELECT {', '.join(_BLOCK_COLUMNS)} "
                f"FROM notebook_blocks "
                f"WHERE notebook_id = ? "
                f"ORDER BY position, created_at",
                [row[0]],
            ).fetchall()
        finally:
            con.close()
        return _row_to_notebook(row, [_row_to_block(b) for b in blocks_rows])

    # ── Save ──

    def save_notebook(
        self,
        record: NotebookRecord,
        *,
        save_kind: str = SAVE_KIND_AUTO,
    ) -> NotebookRecord:
        """Write the TipTap document + each block. ``last_saved_at``
        bumps; blocks are reconciled to match ``record.blocks`` (rows
        not in the list are deleted)."""
        if save_kind not in VALID_SAVE_KINDS:
            raise ValueError(
                f"save_notebook: unknown save_kind {save_kind!r}; "
                f"valid: {sorted(VALID_SAVE_KINDS)}"
            )
        content_str = json.dumps(record.content_json or {})

        con = connect_write(self._db_path, purpose="notebooks_save")
        try:
            con.execute(
                "UPDATE notebook_documents "
                "SET content_json = ?, "
                "    last_saved_at = CURRENT_TIMESTAMP, "
                "    title = COALESCE(?, title), "
                "    format_version = ? "
                "WHERE notebook_id = ?",
                [
                    content_str,
                    record.title,
                    int(record.format_version or BLOCK_TAXONOMY_VERSION),
                    record.notebook_id,
                ],
            )

            # Reconcile blocks: upsert the supplied list, then remove
            # any rows whose block_id isn't present. We do not rely on
            # ON CONFLICT (DuckDB supports it, but the row count is
            # small enough that an explicit DELETE-then-INSERT is
            # clearer for the recall-this-pattern audience).
            kept_ids = {b.block_id for b in record.blocks}
            if kept_ids:
                placeholders = ",".join("?" * len(kept_ids))
                con.execute(
                    f"DELETE FROM notebook_blocks "
                    f"WHERE notebook_id = ? "
                    f"  AND block_id NOT IN ({placeholders})",
                    [record.notebook_id, *kept_ids],
                )
            else:
                con.execute(
                    "DELETE FROM notebook_blocks WHERE notebook_id = ?",
                    [record.notebook_id],
                )

            for block in record.blocks:
                self._upsert_block_inside_lock(con, block)

            con.execute(
                "INSERT INTO notebook_save_log "
                "(notebook_id, save_kind, block_count, bytes) "
                "VALUES (?, ?, ?, ?)",
                [
                    record.notebook_id,
                    save_kind,
                    len(record.blocks),
                    len(content_str.encode("utf-8")),
                ],
            )
        finally:
            con.close()

        reloaded = self.load_notebook_by_id(record.notebook_id)
        assert reloaded is not None, "save_notebook: notebook vanished mid-save"
        return reloaded

    def upsert_blocks(
        self,
        notebook_id: str,
        blocks: list[BlockRecord],
    ) -> list[BlockRecord]:
        """Insert or update a list of blocks without touching the
        TipTap document JSON. Used by the auto-populator — it edits
        the structured block index but doesn't rewrite the
        document-level JSON envelope."""
        if not blocks:
            return []
        for b in blocks:
            if b.notebook_id != notebook_id:
                raise ValueError(
                    f"upsert_blocks: block.notebook_id {b.notebook_id!r} "
                    f"does not match {notebook_id!r}"
                )
        con = connect_write(self._db_path, purpose="notebooks_upsert_blocks")
        try:
            for block in blocks:
                self._upsert_block_inside_lock(con, block)
            con.execute(
                "INSERT INTO notebook_save_log "
                "(notebook_id, save_kind, block_count, bytes) "
                "VALUES (?, ?, ?, 0)",
                [notebook_id, SAVE_KIND_AUTO_POPULATE, len(blocks)],
            )
        finally:
            con.close()
        # Re-read so caller gets the canonical post-DB shape (timestamps,
        # COALESCEd content, etc).
        loaded = self.load_notebook_by_id(notebook_id)
        if loaded is None:
            return []
        kept = {b.block_id for b in blocks}
        return [b for b in loaded.blocks if b.block_id in kept]

    def demote_block(
        self,
        block_id: str,
        *,
        demoted: bool = True,
    ) -> BlockRecord:
        """Soft-toggle a block's demoted state. ``demoted=False``
        restores."""
        con = connect_write(self._db_path, purpose="notebooks_demote")
        try:
            if demoted:
                con.execute(
                    "UPDATE notebook_blocks "
                    "SET demoted_at = CURRENT_TIMESTAMP "
                    "WHERE block_id = ? AND demoted_at IS NULL",
                    [block_id],
                )
            else:
                con.execute(
                    "UPDATE notebook_blocks "
                    "SET demoted_at = NULL "
                    "WHERE block_id = ?",
                    [block_id],
                )
        finally:
            con.close()
        return self._load_block(block_id)

    # ── Internals ──

    def _load_block(self, block_id: str) -> BlockRecord:
        con = _connect_for_read(self._db_path)
        try:
            row = con.execute(
                f"SELECT {', '.join(_BLOCK_COLUMNS)} "
                f"FROM notebook_blocks WHERE block_id = ?",
                [block_id],
            ).fetchone()
        finally:
            con.close()
        if row is None:
            raise KeyError(f"block {block_id!r} not found")
        return _row_to_block(row)

    def _upsert_block_inside_lock(
        self,
        con: Any,
        block: BlockRecord,
    ) -> None:
        """Insert-or-update one block. Caller holds the write lock."""
        existing = con.execute(
            "SELECT block_id FROM notebook_blocks WHERE block_id = ?",
            [block.block_id],
        ).fetchone()
        source_ids_json = json.dumps(list(block.source_event_ids))
        content_json = json.dumps(block.content_json or {})
        if existing is None:
            con.execute(
                "INSERT INTO notebook_blocks "
                "(block_id, notebook_id, block_type, source_event_ids, "
                " document_id, content_json, position, demoted_at, "
                " edited_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    block.block_id,
                    block.notebook_id,
                    block.block_type,
                    source_ids_json,
                    block.document_id,
                    content_json,
                    float(block.position),
                    block.demoted_at,
                    block.edited_at,
                ],
            )
        else:
            con.execute(
                "UPDATE notebook_blocks "
                "SET block_type = ?, "
                "    source_event_ids = ?, "
                "    document_id = ?, "
                "    content_json = ?, "
                "    position = ?, "
                "    demoted_at = ?, "
                "    edited_at = ? "
                "WHERE block_id = ?",
                [
                    block.block_type,
                    source_ids_json,
                    block.document_id,
                    content_json,
                    float(block.position),
                    block.demoted_at,
                    block.edited_at,
                    block.block_id,
                ],
            )

        # Provenance many-to-many. Replace-all is simplest; the rowset
        # per block is tiny (1-3 event ids).
        con.execute(
            "DELETE FROM notebook_block_events WHERE block_id = ?",
            [block.block_id],
        )
        for event_id in block.source_event_ids:
            # Resolve the originating event_type from behavior_events.
            # If behavior_events isn't in this DB (tests sometimes
            # isolate), fall back to a blank string. The reward join
            # only needs the (block_id, event_id) pair to function.
            try:
                ev = con.execute(
                    "SELECT event_type FROM behavior_events WHERE event_id = ?",
                    [event_id],
                ).fetchone()
                event_type = ev[0] if ev else ""
            except duckdb.CatalogException:
                event_type = ""
            con.execute(
                "INSERT INTO notebook_block_events "
                "(notebook_id, block_id, event_id, event_type) "
                "VALUES (?, ?, ?, ?)",
                [block.notebook_id, block.block_id, event_id, event_type],
            )


# ── Module-level default ──


_default_persistence: Optional[NotebookPersistence] = None


def get_default_persistence() -> NotebookPersistence:
    """Process-wide default. SPR-09 flips this to AntiekPersistence."""
    global _default_persistence
    if _default_persistence is None:
        _default_persistence = JSONPersistence()
    return _default_persistence


def reset_default_persistence() -> None:
    """Used by tests to clear a tmp-DB-bound persistence between cases."""
    global _default_persistence
    _default_persistence = None


__all__ = [
    "BlockRecord",
    "JSONPersistence",
    "NotebookPersistence",
    "NotebookRecord",
    "SAVE_KIND_AUTO",
    "SAVE_KIND_AUTO_POPULATE",
    "SAVE_KIND_EXPLICIT",
    "VALID_SAVE_KINDS",
    "get_default_persistence",
    "new_block_id",
    "new_notebook_id",
    "reset_default_persistence",
]
