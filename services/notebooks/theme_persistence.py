"""Tier-3 per-theme notebook persistence (SPR-11).

Themes are hand-curated rollups across multiple per-doc notebooks.
This module is the single writer for ``themes`` and ``theme_blocks``
rows, mirroring the structure of ``services.notebooks.persistence``
for Tier 2.

Persistence-protocol coordination with SPR-09
---------------------------------------------
SPR-09 is concurrently swapping ``JSONPersistence`` for
``AntiekPersistence`` inside ``services.notebooks.persistence.
get_default_persistence``. This module DOES NOT touch that factory;
it stores theme rows in its own dedicated tables (the 0003 migration)
that live alongside the Tier-2 tables in the same DuckDB file.

When SPR-09 lands, theme notebooks can additionally be exported as
``.antiek`` files with ``content_class: "theme_notebook"`` — see
``save_theme_as_antiek`` for the dispatch shim. The native-save path
is persistence-agnostic via the SPR-08 ``NotebookPersistence``
Protocol; we keep all on-disk format decisions inside the SPR-09
writer rather than re-implementing them here.

Single-writer invariant
-----------------------
Every write goes through ``runtime.db_lock.connect_write``. Reads
use a non-read-only DuckDB connection (same pattern as
``services.notebooks.persistence._connect_for_read``).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import duckdb

try:
    from runtime.db_lock import connect_write
    from .schema import default_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from services.notebooks.schema import default_db_path  # type: ignore[no-redef]


# ── Identifier minting ──


def new_theme_id() -> str:
    """``thm-<12hex>-<ms epoch>`` — matches the substrate.behavior.api
    convention for grep ergonomics across the polyglot seam."""
    return f"thm-{uuid.uuid4().hex[:12]}-{int(time.time() * 1000)}"


def new_theme_block_id() -> str:
    """``tbk-<12hex>-<ms epoch>``."""
    return f"tbk-{uuid.uuid4().hex[:12]}-{int(time.time() * 1000)}"


# ── Slug normalization ──


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Normalise a free-form theme title into a URL-safe slug.

    Rules:
      - NFKD-normalised, ASCII-only;
      - lowercase;
      - non-alphanumeric runs collapsed to a single hyphen;
      - leading/trailing hyphens stripped;
      - empty result falls back to ``"theme"``.

    Uniqueness per user_id is enforced by the DB UNIQUE constraint;
    callers that want collision-suffixing call
    ``ThemePersistence.allocate_slug`` instead.
    """
    if not title:
        return "theme"
    normalised = unicodedata.normalize("NFKD", title)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii").lower()
    collapsed = _SLUG_RE.sub("-", ascii_only).strip("-")
    return collapsed or "theme"


# ── Records ──


@dataclass
class ThemeBlockRecord:
    """One row out of ``theme_blocks``.

    ``source_block_id`` / ``source_notebook_id`` are NULL for
    operator-authored prose blocks created INSIDE the theme; non-NULL
    for promoted Tier-2 blocks.
    """

    theme_block_id: str
    theme_id: str
    block_type: str
    content_json: dict[str, Any]
    sort_order: float
    source_block_id: Optional[str] = None
    source_notebook_id: Optional[str] = None
    source_document_id: Optional[str] = None
    dismissed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    # Renderer-only fields, populated by ``load_theme`` from JOINs.
    # Not persisted. ``is_stale`` is True when source_block_id is set
    # but the referenced per_doc_notebook_blocks row no longer exists (the
    # source document or block was deleted).
    is_stale: bool = False
    source_document_title: Optional[str] = None
    source_notebook_title: Optional[str] = None


@dataclass
class ThemeRecord:
    """One row out of ``themes`` plus its ordered blocks."""

    theme_id: str
    user_id: str
    slug: str
    title: str
    cover_snippet: Optional[str] = None
    created_at: Optional[datetime] = None
    last_edited_at: Optional[datetime] = None
    blocks: list[ThemeBlockRecord] = field(default_factory=list)


# ── Internals ──


def _connect_for_read(db_path: str) -> "duckdb.DuckDBPyConnection":
    """Non-read-only connection used for SELECT-only paths. See
    ``services.notebooks.persistence._connect_for_read`` for the
    rationale."""
    return duckdb.connect(db_path)


def _ensure_utc(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return None


_THEME_COLUMNS = (
    "theme_id",
    "user_id",
    "slug",
    "title",
    "cover_snippet",
    "created_at",
    "last_edited_at",
)

_THEME_BLOCK_COLUMNS = (
    "theme_block_id",
    "theme_id",
    "source_block_id",
    "source_notebook_id",
    "source_document_id",
    "block_type",
    "content_json",
    "sort_order",
    "dismissed_at",
    "created_at",
)


def _row_to_theme(
    row: tuple[Any, ...], blocks: list[ThemeBlockRecord]
) -> ThemeRecord:
    return ThemeRecord(
        theme_id=row[0],
        user_id=row[1],
        slug=row[2],
        title=row[3],
        cover_snippet=row[4],
        created_at=_ensure_utc(row[5]),
        last_edited_at=_ensure_utc(row[6]),
        blocks=blocks,
    )


def _row_to_theme_block(row: tuple[Any, ...]) -> ThemeBlockRecord:
    content = row[6]
    if isinstance(content, str):
        content = json.loads(content)
    return ThemeBlockRecord(
        theme_block_id=row[0],
        theme_id=row[1],
        source_block_id=row[2],
        source_notebook_id=row[3],
        source_document_id=row[4],
        block_type=row[5],
        content_json=content or {},
        sort_order=float(row[7]),
        dismissed_at=_ensure_utc(row[8]),
        created_at=_ensure_utc(row[9]),
    )


# ── Persistence ──


class ThemePersistence:
    """JSON-into-DuckDB persistence for the Tier-3 per-theme notebook.

    Coordination with SPR-09
    ------------------------
    SPR-09 swaps the *per-document* notebook writer for an
    ``.antiek``-native one. Themes get the same affordance via
    ``save_theme_as_antiek`` (see bottom of file). The DB rows here
    remain the source of truth for the index page + the operator's
    live editing session; ``.antiek`` is the export format.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or default_db_path()

    @property
    def db_path(self) -> str:
        return self._db_path

    # ── Slug allocation ──

    def allocate_slug(self, *, user_id: str, title: str) -> str:
        """Return a unique slug for this user, suffixing ``-2``,
        ``-3`` ... on collision. The DB UNIQUE constraint is the
        authoritative guard; this method just minimises round-trips.
        """
        base = slugify(title)
        candidate = base
        n = 2
        con = _connect_for_read(self._db_path)
        try:
            while True:
                row = con.execute(
                    "SELECT 1 FROM themes WHERE user_id = ? AND slug = ?",
                    [user_id, candidate],
                ).fetchone()
                if row is None:
                    return candidate
                candidate = f"{base}-{n}"
                n += 1
        finally:
            con.close()

    # ── Theme lifecycle ──

    def create_theme(
        self,
        *,
        user_id: str,
        title: str,
        slug: Optional[str] = None,
        cover_snippet: Optional[str] = None,
    ) -> ThemeRecord:
        """Insert a new theme. Slug is auto-allocated if not supplied."""
        theme_id = new_theme_id()
        resolved_slug = slug or self.allocate_slug(user_id=user_id, title=title)
        con = connect_write(self._db_path, purpose="themes_create")
        try:
            con.execute(
                "INSERT INTO themes "
                "(theme_id, user_id, slug, title, cover_snippet) "
                "VALUES (?, ?, ?, ?, ?)",
                [theme_id, user_id, resolved_slug, title, cover_snippet],
            )
        finally:
            con.close()
        loaded = self.load_theme_by_id(theme_id)
        assert loaded is not None, "create_theme: insert failed"
        return loaded

    def get_or_create_theme(
        self,
        *,
        user_id: str,
        title: str,
    ) -> ThemeRecord:
        """If a theme with the slugified ``title`` already exists for
        the user, return it; otherwise create one.

        The promote flow's "+ New theme" path uses this so re-typing
        the same title doesn't strand the operator with duplicate
        themes.
        """
        slug = slugify(title)
        existing = self.load_theme(user_id=user_id, slug=slug)
        if existing is not None:
            return existing
        return self.create_theme(user_id=user_id, title=title, slug=slug)

    def load_theme(
        self, *, user_id: str, slug: str
    ) -> Optional[ThemeRecord]:
        con = _connect_for_read(self._db_path)
        try:
            row = con.execute(
                f"SELECT {', '.join(_THEME_COLUMNS)} "
                f"FROM themes WHERE user_id = ? AND slug = ?",
                [user_id, slug],
            ).fetchone()
            if row is None:
                return None
            blocks = self._load_theme_blocks(con, row[0])
        finally:
            con.close()
        return _row_to_theme(row, blocks)

    def load_theme_by_id(self, theme_id: str) -> Optional[ThemeRecord]:
        con = _connect_for_read(self._db_path)
        try:
            row = con.execute(
                f"SELECT {', '.join(_THEME_COLUMNS)} "
                f"FROM themes WHERE theme_id = ?",
                [theme_id],
            ).fetchone()
            if row is None:
                return None
            blocks = self._load_theme_blocks(con, row[0])
        finally:
            con.close()
        return _row_to_theme(row, blocks)

    def list_themes(
        self,
        *,
        user_id: str,
        sort: str = "last_edited_desc",
    ) -> list[ThemeRecord]:
        """List all themes for a user. ``sort`` is one of
        ``last_edited_desc`` (default) or ``title_asc``.

        Block lists ARE NOT populated by this call — the index page
        only needs ``title``, ``block_count``, ``last_edited_at``,
        ``cover_snippet`` and we expose ``block_count`` via a separate
        ``count_theme_blocks`` helper. Pulling every block for every
        theme would be wasteful on the index render.
        """
        order_by = {
            "last_edited_desc": "last_edited_at DESC",
            "title_asc": "LOWER(title) ASC",
        }.get(sort)
        if order_by is None:
            raise ValueError(
                f"list_themes: unknown sort {sort!r}; "
                "valid: last_edited_desc, title_asc"
            )
        con = _connect_for_read(self._db_path)
        try:
            rows = con.execute(
                f"SELECT {', '.join(_THEME_COLUMNS)} "
                f"FROM themes WHERE user_id = ? "
                f"ORDER BY {order_by}",
                [user_id],
            ).fetchall()
        finally:
            con.close()
        return [_row_to_theme(r, []) for r in rows]

    def count_theme_blocks(self, theme_id: str) -> int:
        """Cheap COUNT(*) used by the index page card."""
        con = _connect_for_read(self._db_path)
        try:
            row = con.execute(
                "SELECT COUNT(*) FROM theme_blocks "
                "WHERE theme_id = ? AND dismissed_at IS NULL",
                [theme_id],
            ).fetchone()
        finally:
            con.close()
        return int(row[0]) if row else 0

    # ── Promote ──

    def promote_block(
        self,
        *,
        theme_id: str,
        source_block_id: str,
    ) -> ThemeBlockRecord:
        """Promote a single Tier-2 block into a theme.

        Looks up the source notebook_block row to:
          1. Validate the source exists (raise KeyError otherwise).
          2. Cache its content_json + block_type into the theme_block
             row so stale-placeholder rendering can show the last-
             known content if the source disappears later.
          3. Read source_notebook_id and source_document_id for the
             back-link rendering.

        sort_order defaults to "current max + 1.0" so new promotions
        land at the bottom; reorder rewrites this.
        """
        con = connect_write(self._db_path, purpose="themes_promote")
        try:
            src = con.execute(
                "SELECT block_type, content_json, notebook_id, document_id "
                "FROM per_doc_notebook_blocks WHERE block_id = ?",
                [source_block_id],
            ).fetchone()
            if src is None:
                raise KeyError(
                    f"promote_block: source notebook_block "
                    f"{source_block_id!r} not found"
                )
            content_json = src[1]
            if isinstance(content_json, str):
                content_json = json.loads(content_json)
            block_type = src[0]
            source_notebook_id = src[2]
            source_document_id = src[3]

            # Next sort_order: max + 1, or 1 if empty.
            max_row = con.execute(
                "SELECT COALESCE(MAX(sort_order), 0) "
                "FROM theme_blocks WHERE theme_id = ?",
                [theme_id],
            ).fetchone()
            next_order = float(max_row[0]) + 1.0 if max_row else 1.0

            theme_block_id = new_theme_block_id()
            con.execute(
                "INSERT INTO theme_blocks "
                "(theme_block_id, theme_id, source_block_id, "
                " source_notebook_id, source_document_id, block_type, "
                " content_json, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    theme_block_id,
                    theme_id,
                    source_block_id,
                    source_notebook_id,
                    source_document_id,
                    block_type,
                    json.dumps(content_json or {}),
                    next_order,
                ],
            )
            con.execute(
                "UPDATE themes SET last_edited_at = CURRENT_TIMESTAMP "
                "WHERE theme_id = ?",
                [theme_id],
            )
        finally:
            con.close()
        return self._load_theme_block(theme_block_id)

    def promote_blocks(
        self,
        *,
        theme_id: str,
        source_block_ids: list[str],
    ) -> list[ThemeBlockRecord]:
        """Multi-select promote. Order is preserved in the supplied
        list — first id gets the lowest new sort_order."""
        return [
            self.promote_block(theme_id=theme_id, source_block_id=sid)
            for sid in source_block_ids
        ]

    def insert_prose_block(
        self,
        *,
        theme_id: str,
        content_json: dict[str, Any],
        after_sort_order: Optional[float] = None,
    ) -> ThemeBlockRecord:
        """Author a new prose block INSIDE the theme. Tier-3 framing
        is the explicit point of the theme notebook (the SPR-08
        no-authoring rule was Tier-2-only)."""
        con = connect_write(self._db_path, purpose="themes_insert_prose")
        try:
            if after_sort_order is None:
                max_row = con.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) "
                    "FROM theme_blocks WHERE theme_id = ?",
                    [theme_id],
                ).fetchone()
                next_order = float(max_row[0]) + 1.0 if max_row else 1.0
            else:
                next_order = float(after_sort_order) + 0.5
            theme_block_id = new_theme_block_id()
            con.execute(
                "INSERT INTO theme_blocks "
                "(theme_block_id, theme_id, source_block_id, "
                " source_notebook_id, source_document_id, block_type, "
                " content_json, sort_order) "
                "VALUES (?, ?, NULL, NULL, NULL, 'prose', ?, ?)",
                [
                    theme_block_id,
                    theme_id,
                    json.dumps(content_json or {}),
                    next_order,
                ],
            )
            con.execute(
                "UPDATE themes SET last_edited_at = CURRENT_TIMESTAMP "
                "WHERE theme_id = ?",
                [theme_id],
            )
        finally:
            con.close()
        return self._load_theme_block(theme_block_id)

    # ── Reorder + remove ──

    def reorder_blocks(
        self,
        *,
        theme_id: str,
        ordered_theme_block_ids: list[str],
    ) -> list[ThemeBlockRecord]:
        """Assign sort_order = 1.0, 2.0, ... in the supplied order.

        Operating on the full list (not deltas) makes the operation
        idempotent — a partial-write resends the full list rather
        than reasoning about pending fractional positions.
        """
        con = connect_write(self._db_path, purpose="themes_reorder")
        try:
            for position, tbid in enumerate(ordered_theme_block_ids, start=1):
                con.execute(
                    "UPDATE theme_blocks "
                    "SET sort_order = ? "
                    "WHERE theme_block_id = ? AND theme_id = ?",
                    [float(position), tbid, theme_id],
                )
            con.execute(
                "UPDATE themes SET last_edited_at = CURRENT_TIMESTAMP "
                "WHERE theme_id = ?",
                [theme_id],
            )
        finally:
            con.close()
        return self.load_theme_by_id(theme_id).blocks if self.load_theme_by_id(theme_id) else []

    def remove_block(self, *, theme_block_id: str) -> None:
        """Delete a theme_block row. The source Tier-2 block is
        UNTOUCHED — only the theme association goes away."""
        con = connect_write(self._db_path, purpose="themes_remove_block")
        try:
            row = con.execute(
                "SELECT theme_id FROM theme_blocks WHERE theme_block_id = ?",
                [theme_block_id],
            ).fetchone()
            con.execute(
                "DELETE FROM theme_blocks WHERE theme_block_id = ?",
                [theme_block_id],
            )
            if row is not None:
                con.execute(
                    "UPDATE themes SET last_edited_at = CURRENT_TIMESTAMP "
                    "WHERE theme_id = ?",
                    [row[0]],
                )
        finally:
            con.close()

    def dismiss_stale(self, *, theme_block_id: str) -> None:
        """Mark a stale placeholder as dismissed. The row stays in
        the DB so the historical promotion is auditable, but it
        stops rendering."""
        con = connect_write(self._db_path, purpose="themes_dismiss_stale")
        try:
            con.execute(
                "UPDATE theme_blocks "
                "SET dismissed_at = CURRENT_TIMESTAMP "
                "WHERE theme_block_id = ? AND dismissed_at IS NULL",
                [theme_block_id],
            )
        finally:
            con.close()

    # ── Theme-level helpers ──

    def update_theme(
        self,
        *,
        theme_id: str,
        title: Optional[str] = None,
        cover_snippet: Optional[str] = None,
    ) -> ThemeRecord:
        """Patch theme title / cover_snippet. Slug stays fixed even
        if title changes — operator URLs don't break, and the index
        page shows the new title regardless."""
        con = connect_write(self._db_path, purpose="themes_update")
        try:
            con.execute(
                "UPDATE themes "
                "SET title = COALESCE(?, title), "
                "    cover_snippet = COALESCE(?, cover_snippet), "
                "    last_edited_at = CURRENT_TIMESTAMP "
                "WHERE theme_id = ?",
                [title, cover_snippet, theme_id],
            )
        finally:
            con.close()
        loaded = self.load_theme_by_id(theme_id)
        assert loaded is not None, "update_theme: theme vanished mid-update"
        return loaded

    def list_themes_for_source_block(
        self, *, source_block_id: str
    ) -> list[ThemeRecord]:
        """Reverse lookup used by the per-doc surface to show
        "in theme: <title>" on a block that has been promoted."""
        con = _connect_for_read(self._db_path)
        try:
            rows = con.execute(
                f"SELECT DISTINCT {', '.join('t.' + c for c in _THEME_COLUMNS)} "
                f"FROM themes t JOIN theme_blocks tb "
                f"  ON tb.theme_id = t.theme_id "
                f"WHERE tb.source_block_id = ? "
                f"  AND tb.dismissed_at IS NULL "
                f"ORDER BY t.last_edited_at DESC",
                [source_block_id],
            ).fetchall()
        finally:
            con.close()
        return [_row_to_theme(r, []) for r in rows]

    # ── Internals ──

    def _load_theme_block(self, theme_block_id: str) -> ThemeBlockRecord:
        con = _connect_for_read(self._db_path)
        try:
            row = con.execute(
                f"SELECT {', '.join(_THEME_BLOCK_COLUMNS)} "
                f"FROM theme_blocks WHERE theme_block_id = ?",
                [theme_block_id],
            ).fetchone()
        finally:
            con.close()
        if row is None:
            raise KeyError(
                f"theme_block {theme_block_id!r} not found"
            )
        return _row_to_theme_block(row)

    def _load_theme_blocks(
        self,
        con: "duckdb.DuckDBPyConnection",
        theme_id: str,
    ) -> list[ThemeBlockRecord]:
        """Load theme_blocks in sort_order AND detect staleness.

        Stale detection uses a LEFT JOIN against ``per_doc_notebook_blocks``:
        if ``source_block_id`` is set but the LEFT-joined row is NULL,
        the source has been deleted and we flip ``is_stale = True``.
        The renderer uses the cached ``content_json`` to show a
        "last-known content" placeholder.

        We deliberately surface ``dismissed_at IS NULL`` only — the
        operator-dismissed placeholders stay in the DB for audit but
        do not render.
        """
        rows = con.execute(
            f"SELECT tb.theme_block_id, tb.theme_id, tb.source_block_id, "
            f"       tb.source_notebook_id, tb.source_document_id, "
            f"       tb.block_type, tb.content_json, tb.sort_order, "
            f"       tb.dismissed_at, tb.created_at, "
            f"       CASE WHEN tb.source_block_id IS NOT NULL "
            f"                  AND nb.block_id IS NULL "
            f"            THEN 1 ELSE 0 END AS is_stale, "
            f"       nd.title AS source_notebook_title "
            f"FROM theme_blocks tb "
            f"LEFT JOIN per_doc_notebook_blocks nb "
            f"  ON nb.block_id = tb.source_block_id "
            f"LEFT JOIN notebook_documents nd "
            f"  ON nd.notebook_id = tb.source_notebook_id "
            f"WHERE tb.theme_id = ? AND tb.dismissed_at IS NULL "
            f"ORDER BY tb.sort_order, tb.created_at",
            [theme_id],
        ).fetchall()
        out: list[ThemeBlockRecord] = []
        for row in rows:
            block = _row_to_theme_block(row[:10])
            block.is_stale = bool(row[10])
            block.source_notebook_title = row[11]
            out.append(block)
        return out


# ── .antiek native-save shim (SPR-09 integration) ──


def save_theme_as_antiek(
    theme: ThemeRecord,
    *,
    out_path: str,
    persistence: Optional[Any] = None,
) -> str:
    """Export a theme as an ``.antiek`` container.

    Delegates to ``services.antiek_format`` when SPR-09 lands. Until
    then, we ship a JSON shim with the same manifest shape so the
    Save-as menu works and the format-version + content_class bytes
    are deterministic for the round-trip test (M5).

    The manifest carries ``source_notebook_ids`` — the per-doc
    notebooks this theme draws from. SPR-09 readers preserve this
    field; operators can use it to know which source notebooks must
    accompany a shared theme file.

    Parameters
    ----------
    theme : ThemeRecord
        The theme to export. ``theme.blocks`` MUST be the populated
        list (i.e. fetched via ``load_theme`` / ``load_theme_by_id``,
        not the empty list from ``list_themes``).
    out_path : str
        Destination path on disk. Parent directories are created.
    persistence : Optional[NotebookPersistence]
        Unused at SPR-11; reserved for SPR-09's
        ``AntiekPersistence`` injection. We accept it so callers can
        pass ``get_default_persistence()`` without conditional logic.
    """
    del persistence  # SPR-09 placeholder
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    source_notebook_ids = sorted(
        {
            b.source_notebook_id
            for b in theme.blocks
            if b.source_notebook_id is not None
        }
    )

    envelope = {
        "antiek_format_version": 1,
        "content_class": "theme_notebook",
        "manifest": {
            "theme_id": theme.theme_id,
            "user_id": theme.user_id,
            "slug": theme.slug,
            "title": theme.title,
            "cover_snippet": theme.cover_snippet,
            "source_notebook_ids": source_notebook_ids,
            "created_at": (
                theme.created_at.isoformat() if theme.created_at else None
            ),
            "last_edited_at": (
                theme.last_edited_at.isoformat()
                if theme.last_edited_at
                else None
            ),
        },
        "blocks": [
            {
                "theme_block_id": b.theme_block_id,
                "block_type": b.block_type,
                "source_block_id": b.source_block_id,
                "source_notebook_id": b.source_notebook_id,
                "source_document_id": b.source_document_id,
                "content_json": b.content_json,
                "sort_order": b.sort_order,
            }
            for b in theme.blocks
        ],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, sort_keys=True)
    return out_path


def load_theme_from_antiek(path: str) -> dict[str, Any]:
    """Read a theme container back. Returns the manifest+blocks dict
    so callers can decide whether to import-as-new or merge."""
    with open(path, "r", encoding="utf-8") as f:
        envelope = json.load(f)
    if envelope.get("content_class") != "theme_notebook":
        raise ValueError(
            f"load_theme_from_antiek: content_class is "
            f"{envelope.get('content_class')!r}; expected 'theme_notebook'"
        )
    return envelope


# ── Module-level default ──


_default_theme_persistence: Optional[ThemePersistence] = None


def get_default_theme_persistence() -> ThemePersistence:
    """Process-wide default. Mirrors
    ``services.notebooks.persistence.get_default_persistence`` but
    independent of it; SPR-09's swap of the Tier-2 factory does not
    affect this one.
    """
    global _default_theme_persistence
    if _default_theme_persistence is None:
        _default_theme_persistence = ThemePersistence()
    return _default_theme_persistence


def reset_default_theme_persistence() -> None:
    """Used by tests to clear a tmp-DB-bound persistence between cases."""
    global _default_theme_persistence
    _default_theme_persistence = None


__all__ = [
    "ThemeBlockRecord",
    "ThemePersistence",
    "ThemeRecord",
    "get_default_theme_persistence",
    "load_theme_from_antiek",
    "new_theme_block_id",
    "new_theme_id",
    "reset_default_theme_persistence",
    "save_theme_as_antiek",
    "slugify",
]
