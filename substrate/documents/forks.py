"""The document fork primitive (thread-merge + document fork SPR-01).

A fork is a named, first-class DIVERGENT version of a document: a real
library document with a lineage row. The parent's body is COPIED IN FULL at
fork time — operator-scale data makes the copy cheap, and the capture reuses
the source-merge snapshot discipline (before/after body hashes,
source_merge.py's SourceMergeCommitReceipt shape) so a fork's provenance is
as auditable as a merge commit. A fork is NOT a source-merge commit: no
before/after restore semantics against the original, and the original is
NEVER written by any path in this module.

Additive idempotent DDL under the write lock, CHECK constraints mirroring
the API-layer validation (the unit-1 highlights / reading-state convention):

  document_forks (
    fork_id            VARCHAR PK,
    owner_user_id      VARCHAR,
    parent_document_id VARCHAR,
    fork_document_id   VARCHAR UNIQUE,     -- one fork line per document
    operation_id       VARCHAR,            -- the client's idempotency key
    fork_point_locator VARCHAR NULL,       -- page index / unit-1 anchor ref
    note               VARCHAR NULL,       -- length-capped
    generation_id      VARCHAR NULL,       -- the reformat promote path's ref
    parent_body_sha256 VARCHAR CHECK (64), -- capture discipline
    fork_body_sha256   VARCHAR CHECK (64),
    created_at         TIMESTAMPTZ,
    UNIQUE (owner_user_id, operation_id)
  )

Two creation modes, both through this module:

  - COPY (the reader's "fork this book"): the parent's body is copied in
    full into a NEW document, registered through the rights chokepoint
    (register_source_document) with the class the derivation rule
    (rights/register.py derived_content_class) mandates — a fork of a
    gated class (restricted_pending_opt_in / personal_reading, and the
    deny-by-default NULL) is REFUSED, which is strictly stronger than the
    spec's "stays owner-only": the laundering path cannot exist.
  - ADOPT (the reformat flow's "officially fork", reformat-provenance
    spec: "the lineage row carries the generation record"): an existing
    PROVISIONAL derived document is promoted to the named divergent
    version — no body copy (its body is its own), the lineage row records
    both bodies' hashes at capture and carries the generation id.

Fork-of-fork is DEPTH-1 this wave, refused honestly (ForkDepthLimitError →
the route's 409 names the limit): a fork can neither be forked nor adopt a
document that already has forks.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from runtime.db_lock import LockedConnection
from substrate.books.model import get_book_asset, upsert_book_asset
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS
from substrate.graph.ops import insert_document, new_random_id
from substrate.rights.register import (
    SourceKind,
    derived_content_class,
    register_source_document,
)

#: Length caps, enforced at the API AND as CHECKs here (the two-layer rule).
NOTE_MAX_CHARS = 500
LOCATOR_MAX_CHARS = 200
OPERATION_ID_MAX_CHARS = 100

DDL = """
CREATE TABLE IF NOT EXISTS document_forks (
  fork_id VARCHAR PRIMARY KEY,
  owner_user_id VARCHAR NOT NULL,
  parent_document_id VARCHAR NOT NULL,
  fork_document_id VARCHAR NOT NULL UNIQUE,
  operation_id VARCHAR NOT NULL CHECK (length(operation_id) <= 100),
  fork_point_locator VARCHAR CHECK (
    fork_point_locator IS NULL OR length(fork_point_locator) <= 200
  ),
  note VARCHAR CHECK (note IS NULL OR length(note) <= 500),
  generation_id VARCHAR,
  parent_body_sha256 VARCHAR NOT NULL CHECK (length(parent_body_sha256) = 64),
  fork_body_sha256 VARCHAR NOT NULL CHECK (length(fork_body_sha256) = 64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (owner_user_id, operation_id)
);
"""


def init_forks_schema(con: LockedConnection) -> None:
    """Create the additive fork schema on an existing writer connection
    (idempotent — CREATE TABLE IF NOT EXISTS throughout)."""
    con.execute(DDL)


def forks_table_exists(con: object) -> bool:
    """Whether the table is present (read paths must not run DDL — a CREATE
    on a read connection fails, and a GET acquires no write lock for this)."""
    row = con.execute(  # type: ignore[attr-defined]
        "SELECT 1 FROM duckdb_tables() WHERE table_name = 'document_forks' LIMIT 1"
    ).fetchone()
    return row is not None


class SqlExecutor(Protocol):
    """The one call every connection in this package needs (the highlights
    convention): write side (LockedConnection) and read side
    (connect_read's DuckDBPyConnection) both satisfy it structurally."""

    def execute(self, sql: str, parameters: Any = None) -> Any: ...


class ForkDepthLimitError(ValueError):
    """Fork-of-fork is depth-1 this wave: the named, honest refusal."""


class ForkConflictError(ValueError):
    """The document is already a fork of a DIFFERENT parent (a document has
    exactly one fork line — fork_document_id is UNIQUE)."""


@dataclass(frozen=True, slots=True)
class DocumentForkRow:
    """One lineage row: fork id · parent · fork · capture hashes."""

    fork_id: str
    owner_user_id: str
    parent_document_id: str
    fork_document_id: str
    operation_id: str
    fork_point_locator: str | None
    note: str | None
    generation_id: str | None
    parent_body_sha256: str
    fork_body_sha256: str
    created_at: str


def _to_row(r: Any) -> DocumentForkRow:
    return DocumentForkRow(
        fork_id=str(r[0]),
        owner_user_id=str(r[1]),
        parent_document_id=str(r[2]),
        fork_document_id=str(r[3]),
        operation_id=str(r[4]),
        fork_point_locator=None if r[5] is None else str(r[5]),
        note=None if r[6] is None else str(r[6]),
        generation_id=None if r[7] is None else str(r[7]),
        parent_body_sha256=str(r[8]),
        fork_body_sha256=str(r[9]),
        created_at=str(r[10]),
    )


_SELECT = (
    "SELECT fork_id, owner_user_id, parent_document_id, fork_document_id, "
    "operation_id, fork_point_locator, note, generation_id, "
    "parent_body_sha256, fork_body_sha256, created_at FROM document_forks"
)


def _body_sha256(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"fork writes require a LockedConnection (got "
            f"{type(con).__name__}). Use runtime.db_lock.connect_write(db_path)."
        )


class DocumentForkStore:
    """Create forks and answer lineage, owner-scoped throughout."""

    # ── Reads (any connection; read-safe before the table exists) ────────

    def get(
        self, con: SqlExecutor, *, owner_user_id: str, fork_id: str
    ) -> DocumentForkRow | None:
        if not forks_table_exists(con):
            return None
        row = con.execute(
            f"{_SELECT} WHERE owner_user_id = ? AND fork_id = ? LIMIT 1",
            [owner_user_id, fork_id],
        ).fetchone()
        return None if row is None else _to_row(row)

    def forks_of(
        self, con: SqlExecutor, *, owner_user_id: str, document_id: str
    ) -> list[DocumentForkRow]:
        """Forks OF this document (the children direction), newest last."""
        if not forks_table_exists(con):
            return []
        rows = con.execute(
            f"{_SELECT} WHERE owner_user_id = ? AND parent_document_id = ? "
            "ORDER BY created_at, fork_id",
            [owner_user_id, document_id],
        ).fetchall()
        return [_to_row(r) for r in rows]

    def forked_from(
        self, con: SqlExecutor, *, owner_user_id: str, document_id: str
    ) -> DocumentForkRow | None:
        """The lineage row where this document IS the fork (the parent
        direction), or None when it is not a fork."""
        if not forks_table_exists(con):
            return None
        row = con.execute(
            f"{_SELECT} WHERE owner_user_id = ? AND fork_document_id = ? LIMIT 1",
            [owner_user_id, document_id],
        ).fetchone()
        return None if row is None else _to_row(row)

    def lineage(
        self, con: SqlExecutor, *, owner_user_id: str, fork_id: str
    ) -> tuple[DocumentForkRow, list[DocumentForkRow]] | None:
        """The row plus its children rows (one row per hop; depth-1 this
        wave, so a fork's children list is honestly empty)."""
        row = self.get(con, owner_user_id=owner_user_id, fork_id=fork_id)
        if row is None:
            return None
        children = self.forks_of(
            con, owner_user_id=owner_user_id, document_id=row.fork_document_id
        )
        return row, children

    # ── Writes (LockedConnection only) ────────────────────────────────────

    def create_copy_fork(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        parent_document_id: str,
        operation_id: str,
        note: str | None = None,
        fork_point_locator: str | None = None,
    ) -> tuple[DocumentForkRow, bool]:
        """Fork a document by COPYING its body in full into a new document.

        Idempotent on (owner, operation_id): a replay returns the existing
        row with created=False. Raises KeyError when the parent is missing
        or not the owner's (the route's 404), ForkDepthLimitError when the
        parent is itself a fork, DerivationRefusedError when the parent's
        rights class grants no transformation right, and ValueError when
        the parent has no body to copy (a takedown-nulled row)."""
        _require_locked(con)
        init_forks_schema(con)
        existing = self._by_operation(
            con, owner_user_id=owner_user_id, operation_id=operation_id
        )
        if existing is not None:
            return existing, False
        parent = self._owned_document(con, owner_user_id, parent_document_id)
        if parent is None:
            raise KeyError(parent_document_id)
        self._refuse_depth_two(con, parent_document_id)
        (
            title,
            author,
            published_at,
            source_tier,
            document_type,
            raw_text,
            metadata,
            content_class,
            ip_holder_id,
        ) = parent
        # Deny-by-default: a NULL class (a legacy row) forks like the gated
        # default — the derivation rule refuses it, never a silent serve.
        derived = derived_content_class(content_class or GATED_DEFAULT_CONTENT_CLASS)
        if raw_text is None:
            raise ValueError(
                f"{parent_document_id} has no body to copy (its raw_text is "
                "NULL — a takedown path) — there is nothing to fork"
            )
        # The derivation table's fixed-point rows keep the rights basis, so
        # the rights holder follows the derivative; a rebasis to user_owned
        # (public_domain's derivative) drops it — the fork is the operator's
        # own expression.
        inherited_ip = ip_holder_id if derived == content_class else None
        fork_document_id = new_random_id("doc")
        insert_document(
            con,
            document_id=fork_document_id,
            source_tier=int(source_tier),
            document_type=str(document_type),
            title=None if title is None else str(title),
            author=None if author is None else str(author),
            published_at=published_at,
            raw_text=raw_text,
            metadata=None if metadata is None else str(metadata),
            content_class=derived,
            ip_holder_id=inherited_ip,
            owner_user_id=owner_user_id,
        )
        register_source_document(
            con,
            document_id=fork_document_id,
            # The Read workflow's tag (register_book's precedent: every
            # Read-path book registers LICENSED_PUBLISHER; the kind is not
            # persisted — it drives only the escrow-exclusion check).
            source_kind=SourceKind.LICENSED_PUBLISHER,
            content_class=derived,
            ip_holder_id=inherited_ip,
        )
        self._copy_chunks(con, parent_document_id, fork_document_id)
        self._copy_book_asset(con, parent_document_id, fork_document_id)
        # Capture discipline: hash what was actually STORED, not what was
        # asked for (the insert path's guard may transform the body).
        stored_body = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ? LIMIT 1",
            [fork_document_id],
        ).fetchone()
        fork_hash = _body_sha256(str(stored_body[0])) if stored_body else ""
        row = self._insert_lineage(
            con,
            owner_user_id=owner_user_id,
            parent_document_id=parent_document_id,
            fork_document_id=fork_document_id,
            operation_id=operation_id,
            fork_point_locator=fork_point_locator,
            note=note,
            generation_id=None,
            parent_body_sha256=_body_sha256(raw_text),
            fork_body_sha256=fork_hash,
        )
        return row, True

    def adopt_fork(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        parent_document_id: str,
        derived_document_id: str,
        generation_id: str | None,
        operation_id: str,
        note: str | None = None,
        fork_point_locator: str | None = None,
    ) -> tuple[DocumentForkRow, bool]:
        """Promote an existing PROVISIONAL derived document to the named
        fork (the reformat flow's "officially fork" — reformat-provenance
        spec: the lineage row carries the generation record). No body copy:
        the derived document's body is its own, registered at birth by the
        reformat pipeline. Idempotent on (owner, operation_id) AND naturally
        on the derived document (fork_document_id UNIQUE): re-adopting the
        same derived document under the same parent returns the row.

        Raises KeyError when either document is missing or not the owner's,
        ForkDepthLimitError when the parent is itself a fork or the derived
        document already has forks, ForkConflictError when the derived
        document is already a fork of a DIFFERENT parent, and ValueError
        when the generation ref does not resolve to this derived document."""
        _require_locked(con)
        init_forks_schema(con)
        existing = self._by_operation(
            con, owner_user_id=owner_user_id, operation_id=operation_id
        )
        if existing is not None:
            return existing, False
        if derived_document_id == parent_document_id:
            raise ValueError("a document cannot be forked onto itself")
        parent = self._owned_document(con, owner_user_id, parent_document_id)
        if parent is None:
            raise KeyError(parent_document_id)
        derived = self._owned_document(con, owner_user_id, derived_document_id)
        if derived is None:
            raise KeyError(derived_document_id)
        prior = self.forked_from(
            con, owner_user_id=owner_user_id, document_id=derived_document_id
        )
        if prior is not None:
            if prior.parent_document_id == parent_document_id:
                return prior, False
            raise ForkConflictError(
                f"{derived_document_id} is already a fork of "
                f"{prior.parent_document_id} — a document has exactly one "
                "fork line"
            )
        self._refuse_depth_two(con, parent_document_id)
        if self.forks_of(
            con, owner_user_id=owner_user_id, document_id=derived_document_id
        ):
            raise ForkDepthLimitError(
                f"{derived_document_id} already has forks of its own — "
                "adopting it as a fork would make depth-2 lineage"
            )
        if generation_id is not None:
            self._require_generation(
                con,
                owner_user_id=owner_user_id,
                generation_id=generation_id,
                parent_document_id=parent_document_id,
                derived_document_id=derived_document_id,
            )
        parent_body = parent[5]
        derived_body = derived[5]
        if parent_body is None or derived_body is None:
            raise ValueError(
                "both documents must carry a body for the capture hashes — "
                "a takedown-nulled row cannot enter a fork line"
            )
        row = self._insert_lineage(
            con,
            owner_user_id=owner_user_id,
            parent_document_id=parent_document_id,
            fork_document_id=derived_document_id,
            operation_id=operation_id,
            fork_point_locator=fork_point_locator,
            note=note,
            generation_id=generation_id,
            parent_body_sha256=_body_sha256(str(parent_body)),
            fork_body_sha256=_body_sha256(str(derived_body)),
        )
        return row, True

    # ── Internals ─────────────────────────────────────────────────────────

    def _by_operation(
        self, con: SqlExecutor, *, owner_user_id: str, operation_id: str
    ) -> DocumentForkRow | None:
        row = con.execute(
            f"{_SELECT} WHERE owner_user_id = ? AND operation_id = ? LIMIT 1",
            [owner_user_id, operation_id],
        ).fetchone()
        return None if row is None else _to_row(row)

    def _owned_document(
        self, con: SqlExecutor, owner_user_id: str, document_id: str
    ) -> tuple[Any, ...] | None:
        """The document row's fork-relevant columns, or None when missing
        or owned by someone else (existence never crosses the owner line)."""
        row = con.execute(
            "SELECT title, author, published_at, source_tier, document_type, "
            "raw_text, metadata, content_class, ip_holder_id FROM documents "
            "WHERE document_id = ? AND owner_user_id = ? LIMIT 1",
            [document_id, owner_user_id],
        ).fetchone()
        return None if row is None else tuple(row)

    def _refuse_depth_two(self, con: SqlExecutor, parent_document_id: str) -> None:
        """Depth-1 this wave: a fork may not be forked (the parent must not
        itself be a fork). Owner-agnostic on purpose — the limit is about
        the lineage shape, and refusal never reveals ownership (the parent
        check has already run owner-scoped)."""
        row = con.execute(
            "SELECT 1 FROM document_forks WHERE fork_document_id = ? LIMIT 1",
            [parent_document_id],
        ).fetchone()
        if row is not None:
            raise ForkDepthLimitError(
                f"{parent_document_id} is itself a fork — fork-of-fork is "
                "depth-1 this wave (fork_depth_limit)"
            )

    def _require_generation(
        self,
        con: SqlExecutor,
        *,
        owner_user_id: str,
        generation_id: str,
        parent_document_id: str,
        derived_document_id: str,
    ) -> None:
        """The lineage row carries the generation RECORD, so the ref must
        resolve — to a record of THIS owner, for THIS derived document, from
        THIS parent. A dangling or mismatched ref is a 422, never stored."""
        from substrate.provenance.store import ProvenanceStore

        record = ProvenanceStore().get_generation(con, generation_id)
        if (
            record is None
            or record.owner_user_id != owner_user_id
            or record.derived_document_id != derived_document_id
            or record.source_document_id != parent_document_id
        ):
            raise ValueError(
                f"generation_id {generation_id!r} does not resolve to a "
                "generation record of this owner for this derived document "
                "from this parent"
            )

    def _copy_chunks(
        self, con: LockedConnection, parent_document_id: str, fork_document_id: str
    ) -> None:
        """The body copy includes the parent's chunks, re-keyed to the fork
        (chunk ids are content-addressed across the corpus, so the fork's
        rows take document-scoped ids — the reformat pipeline's convention
        ``{document_id}-b{ordinal}``)."""
        rows = con.execute(
            "SELECT chunk_index, section_path, text, embedding, token_count "
            "FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            [parent_document_id],
        ).fetchall()
        for chunk_index, section_path, text, embedding, token_count in rows:
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
                "section_path, text, embedding, token_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    f"{fork_document_id}-c{int(chunk_index)}",
                    fork_document_id,
                    int(chunk_index),
                    section_path,
                    text,
                    embedding,
                    int(token_count),
                ],
            )

    def _copy_book_asset(
        self, con: LockedConnection, parent_document_id: str, fork_document_id: str
    ) -> None:
        """The reader's book detail route 404s without a book_assets row, so
        the fork carries the parent's structure (toc, pagination, cover,
        provenance prose). Takedown state is NOT copied — a taken-down
        parent is gated out by the derivation rule before this runs."""
        asset = get_book_asset(con, parent_document_id)
        if asset is None:
            return
        upsert_book_asset(
            con,
            document_id=fork_document_id,
            toc=asset.toc,
            page_count=asset.page_count,
            pagination_scheme=asset.pagination_scheme,
            cover_uri=asset.cover_uri,
            provenance=asset.provenance,
            license_basis=asset.license_basis,
        )

    def _insert_lineage(
        self,
        con: LockedConnection,
        *,
        owner_user_id: str,
        parent_document_id: str,
        fork_document_id: str,
        operation_id: str,
        fork_point_locator: str | None,
        note: str | None,
        generation_id: str | None,
        parent_body_sha256: str,
        fork_body_sha256: str,
    ) -> DocumentForkRow:
        fork_id = new_random_id("fork")
        con.execute(
            "INSERT INTO document_forks (fork_id, owner_user_id, "
            "parent_document_id, fork_document_id, operation_id, "
            "fork_point_locator, note, generation_id, parent_body_sha256, "
            "fork_body_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                fork_id,
                owner_user_id,
                parent_document_id,
                fork_document_id,
                operation_id,
                fork_point_locator,
                note,
                generation_id,
                parent_body_sha256,
                fork_body_sha256,
            ],
        )
        row = self.get(con, owner_user_id=owner_user_id, fork_id=fork_id)
        if row is None:  # unreachable: the insert just landed in this txn
            raise RuntimeError("document_forks insert did not read back")
        return row
