"""Notebook surface — Wedge 2 linchpin (Sprint 18-19, master-spec §4.2).

TipTap-based literate-analysis documents combining:
- markdown prose
- PDF region references
- claim cards (live claim_id references)
- note references
- open-question cards
- cross-doc-link bridges
- chat-exchange snippets
- MASTER.md section references
- image artifacts
- LaTeX equations

**Substrate references are live-pulled at render time, not denormalized
into the notebook JSON.** The notebook stores reference IDs; the
renderer resolves current substrate state on each fetch. Per
master-spec §13.2: substrate-is-source-of-truth invariant.

When a referenced object is deleted, the renderer surfaces a tombstone
block: ``"This claim was deleted on YYYY-MM-DD; prior text was..."``
per master-spec §16.4 substrate-reference freshness mechanism.

Per master-spec §14.3 sequencing discipline: **Wedge 2 notebook is
the linchpin.** PostHog Wedges 3 (command palette), 4 (ubiquitous AI),
and 5 (trajectory replay) all chain off this surface. Sprints 18-19
must not slip it.
"""

from __future__ import annotations

import contextlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .authority import NotebookAccountAuthority, NotebookAuthority
from .migration import EMPTY_DOCUMENT_SHA256, canonical_document_sha256

# Block types — must match the SQL CHECK constraint in
# substrate/graph/schema.py:notebook_blocks.block_type.
VALID_BLOCK_TYPES: frozenset[str] = frozenset({
    "prose",
    "region_embed",
    "claim_card",
    "note",
    "question_card",
    "cross_doc_link",
    "chat_exchange",
    "master_md_section",
    "image",
    "latex",
})


VALID_NOTEBOOK_CONTENT_CLASSES: frozenset[str] = frozenset({
    "user_owned",                 # private; 50% margin per §13.5
    "user_public_contribution",   # public; ad-supported + 70% creator rev-share
})


@dataclass
class NotebookBlock:
    block_id: str
    notebook_id: str
    block_index: int
    block_type: str
    ref_id: str | None  # substrate reference (claim_id, note_id, etc); NULL for prose/latex
    content_json: dict
    created_at: str


@dataclass
class Notebook:
    notebook_id: str
    title: str
    investigation_id: str | None
    document_id: str | None
    owner_user_id: str
    content_class: str
    schema_version: int
    revision: int
    content_sha256: str
    created_at: str
    updated_at: str
    metadata: dict = field(default_factory=dict)
    blocks: list[NotebookBlock] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class NotebookMutationReceipt:
    schema_version: int
    notebook_id: str
    revision: int
    content_sha256: str
    replayed: bool


class NotebookStorageError(RuntimeError):
    pass


class NotebookCorruptError(NotebookStorageError):
    pass


class NotebookAlreadyExists(NotebookStorageError):
    pass


class NotebookNotFoundError(NotebookStorageError):
    pass


class NotebookMutationConflict(NotebookStorageError):
    def __init__(self, code: str, *, revision: int, content_sha256: str) -> None:
        super().__init__(code)
        self.code = code
        self.revision = revision
        self.content_sha256 = content_sha256


class NotebookEmptyDocumentConflict(NotebookMutationConflict):
    def __init__(
        self,
        *,
        revision: int,
        content_sha256: str,
        existing_block_count: int,
    ) -> None:
        super().__init__(
            "empty_doc_would_destroy_blocks",
            revision=revision,
            content_sha256=content_sha256,
        )
        self.existing_block_count = existing_block_count


def _require_authority(authority: NotebookAuthority) -> NotebookAuthority:
    if not isinstance(authority, NotebookAuthority):
        raise TypeError("NotebookAuthority is required")
    return authority


def _investigation_digest(authority: NotebookAuthority, investigation_id: str | None) -> str | None:
    if investigation_id is None:
        return None
    from substrate.investigation_tenancy import InvestigationAuthority

    return InvestigationAuthority(authority.account_id, investigation_id).investigation_digest


@contextlib.contextmanager
def _mutation(con: Any):
    con.execute("BEGIN TRANSACTION")
    try:
        yield
    except Exception:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def _decode_json_object(value: Any, *, field_name: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise NotebookCorruptError(f"notebook {field_name} is unavailable") from exc
    if not isinstance(decoded, dict):
        raise NotebookCorruptError(f"notebook {field_name} is unavailable")
    return decoded


def _document_from_block_rows(rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    from .tiptap_codec import compose

    blocks = [
        {"content_json": _decode_json_object(row[5], field_name="block content")}
        for row in rows
    ]
    return compose(blocks)


def _block_rows(con: Any, authority: NotebookAuthority) -> list[tuple[Any, ...]]:
    return con.execute(
        "SELECT block_id, notebook_id, block_index, block_type, ref_id, "
        "content_json, created_at FROM notebook_blocks "
        "WHERE account_digest = ? AND notebook_id = ? ORDER BY block_index",
        [authority.account_digest, authority.notebook_id],
    ).fetchall()


def _refresh_content_state(
    con: Any,
    authority: NotebookAuthority,
    *,
    bump_revision: bool,
) -> tuple[int, str]:
    document = _document_from_block_rows(_block_rows(con, authority))
    content_sha256 = canonical_document_sha256(document)
    increment = 1 if bump_revision else 0
    row = con.execute(
        "UPDATE notebooks SET revision = revision + ?, content_sha256 = ?, "
        "updated_at = CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE updated_at END "
        "WHERE account_digest = ? AND notebook_id = ? "
        "RETURNING revision, content_sha256",
        [
            increment,
            content_sha256,
            increment,
            authority.account_digest,
            authority.notebook_id,
        ],
    ).fetchone()
    if row is None:
        raise NotebookStorageError("notebook disappeared during mutation")
    return int(row[0]), str(row[1])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_notebook(
    con: Any,
    authority: NotebookAuthority,
    *,
    title: str,
    investigation_id: str | None = None,
    document_id: str | None = None,
    content_class: str = "user_owned",
    metadata: dict | None = None,
) -> str:
    """Create a notebook. Returns the notebook_id.

    Per master-spec §4.5: notebook starts content_class='user_owned'
    (private); the operator explicitly promotes to
    'user_public_contribution' via a separate action (the §13.9
    quality gate runs at that promotion point)."""
    if content_class not in VALID_NOTEBOOK_CONTENT_CLASSES:
        raise ValueError(
            f"content_class must be in {VALID_NOTEBOOK_CONTENT_CLASSES}, "
            f"got {content_class!r}"
        )
    authority = _require_authority(authority)
    metadata_json = json.dumps(metadata or {})
    with _mutation(con):
        existing = con.execute(
            "SELECT 1 FROM notebooks WHERE account_digest = ? AND notebook_id = ?",
            [authority.account_digest, authority.notebook_id],
        ).fetchone()
        if existing is not None:
            raise NotebookAlreadyExists("notebook already exists")
        con.execute(
            "INSERT INTO notebooks (account_digest, notebook_id, title, "
            "investigation_id, investigation_digest, document_id, owner_user_id, content_class, "
            "schema_version, revision, content_sha256, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)",
            [
                authority.account_digest,
                authority.notebook_id,
                title,
                investigation_id,
                _investigation_digest(authority, investigation_id),
                document_id,
                authority.account_id,
                content_class,
                EMPTY_DOCUMENT_SHA256,
                metadata_json,
            ],
        )
    return authority.notebook_id


def append_block(
    con: Any,
    authority: NotebookAuthority,
    *,
    block_type: str,
    content: dict,
    ref_id: str | None = None,
) -> str:
    """Append a block to the end of a notebook. Block types must match
    VALID_BLOCK_TYPES; the SQL CHECK constraint enforces too.

    ``content`` is the TipTap block JSON (e.g. ``{"text": "..."}`` for
    prose, ``{"region_id": "..."}`` for region_embed). Live substrate
    references go in ``ref_id``; the content dict carries any
    block-local UI state (positioning, collapsed, etc).
    """
    if block_type not in VALID_BLOCK_TYPES:
        raise ValueError(
            f"block_type must be in {VALID_BLOCK_TYPES}, got {block_type!r}"
        )
    authority = _require_authority(authority)
    block_id = f"nbb-{uuid.uuid4().hex[:12]}"
    with _mutation(con):
        if get_notebook(con, authority) is None:
            raise NotebookNotFoundError("notebook not found")
        row = con.execute(
            "SELECT COALESCE(MAX(block_index) + 1, 0) FROM notebook_blocks "
            "WHERE account_digest = ? AND notebook_id = ?",
            [authority.account_digest, authority.notebook_id],
        ).fetchone()
        next_index = int(row[0]) if row else 0
        con.execute(
            "INSERT INTO notebook_blocks (account_digest, block_id, notebook_id, "
            "block_index, block_type, ref_id, content_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                authority.account_digest,
                block_id,
                authority.notebook_id,
                next_index,
                block_type,
                ref_id,
                json.dumps(content),
            ],
        )
        _refresh_content_state(con, authority, bump_revision=True)
    return block_id


def update_block(
    con: Any,
    authority: NotebookAuthority,
    block_id: str,
    *,
    content: dict | None = None,
    ref_id: str | None = None,
    clear_ref_id: bool = False,
) -> bool:
    """Edit one block in place. Returns True if the block was found
    and updated, False if not found.

    - ``content``: when supplied, replaces ``content_json`` in full.
      Pass None to leave it alone.
    - ``ref_id``: when supplied, sets the substrate reference id.
      Pass None and set ``clear_ref_id=True`` to explicitly NULL it.
      Pass None without ``clear_ref_id`` to leave it alone.

    The ``block_type`` is intentionally immutable here — changing
    type would invalidate the SQL CHECK + content_json shape. The UI
    re-creates blocks rather than re-typing them.
    """
    authority = _require_authority(authority)
    with _mutation(con):
        if get_notebook(con, authority) is None:
            return False
        existing = con.execute(
            "SELECT content_json, ref_id FROM notebook_blocks "
            "WHERE account_digest = ? AND notebook_id = ? AND block_id = ?",
            [authority.account_digest, authority.notebook_id, block_id],
        ).fetchone()
        if existing is None:
            return False
        existing_content = _decode_json_object(existing[0], field_name="block content")
        next_content = existing_content if content is None else content
        next_ref_id = existing[1]
        if ref_id is not None:
            next_ref_id = ref_id
        elif clear_ref_id:
            next_ref_id = None
        if next_content == existing_content and next_ref_id == existing[1]:
            return True
        con.execute(
            "UPDATE notebook_blocks SET content_json = ?, ref_id = ? "
            "WHERE account_digest = ? AND notebook_id = ? AND block_id = ?",
            [
                json.dumps(next_content),
                next_ref_id,
                authority.account_digest,
                authority.notebook_id,
                block_id,
            ],
        )
        _refresh_content_state(con, authority, bump_revision=True)
        return True


def delete_block(con: Any, authority: NotebookAuthority, block_id: str) -> bool:
    """Delete one block by ID. Re-numbers the remaining blocks so
    ``block_index`` stays a dense [0..n-1] sequence — the UI assumes
    no gaps. Returns True if the block was deleted, False if not
    found.

    Per master-spec §13.2 substrate-is-source-of-truth: deleting a
    block deletes the row, not just hides it. Any literate-analysis
    notebook that references the deleted block via substrate ref
    surfaces a tombstone at render time."""
    authority = _require_authority(authority)
    with _mutation(con):
        if get_notebook(con, authority) is None:
            return False
        existing = con.execute(
            "SELECT block_index FROM notebook_blocks WHERE account_digest = ? "
            "AND notebook_id = ? AND block_id = ?",
            [authority.account_digest, authority.notebook_id, block_id],
        ).fetchone()
        if existing is None:
            return False
        con.execute(
            "DELETE FROM notebook_blocks WHERE account_digest = ? "
            "AND notebook_id = ? AND block_id = ?",
            [authority.account_digest, authority.notebook_id, block_id],
        )
        rows = con.execute(
            "SELECT block_id FROM notebook_blocks WHERE account_digest = ? "
            "AND notebook_id = ? ORDER BY block_index",
            [authority.account_digest, authority.notebook_id],
        ).fetchall()
        _apply_block_order(con, authority, [str(row[0]) for row in rows])
        _refresh_content_state(con, authority, bump_revision=True)
        return True


def _apply_block_order(
    con: Any,
    authority: NotebookAuthority,
    ordered_block_ids: list[str],
) -> None:
    sentinel_offset = -(int(uuid.uuid4().int >> 96) & 0xFFFFFF) - 1
    for index, block_id in enumerate(ordered_block_ids):
        con.execute(
            "UPDATE notebook_blocks SET block_index = ? WHERE account_digest = ? "
            "AND notebook_id = ? AND block_id = ?",
            [
                sentinel_offset - index,
                authority.account_digest,
                authority.notebook_id,
                block_id,
            ],
        )
    for index, block_id in enumerate(ordered_block_ids):
        con.execute(
            "UPDATE notebook_blocks SET block_index = ? WHERE account_digest = ? "
            "AND notebook_id = ? AND block_id = ?",
            [index, authority.account_digest, authority.notebook_id, block_id],
        )


def reorder_blocks(
    con: Any, authority: NotebookAuthority, *, ordered_block_ids: list[str],
) -> None:
    """Re-order a notebook's blocks by the supplied list. The list
    must be a complete permutation of the notebook's current block_ids
    — partial reorders are rejected to keep the contract simple.

    Raises ``ValueError`` if the supplied list doesn't exactly match
    the notebook's current block set."""
    authority = _require_authority(authority)
    with _mutation(con):
        if get_notebook(con, authority) is None:
            raise NotebookNotFoundError("notebook not found")
        current_list = [
            str(row[0])
            for row in con.execute(
                "SELECT block_id FROM notebook_blocks WHERE account_digest = ? "
                "AND notebook_id = ? ORDER BY block_index",
                [authority.account_digest, authority.notebook_id],
            ).fetchall()
        ]
        current = set(current_list)
        proposed = set(ordered_block_ids)
        if current != proposed or len(current_list) != len(ordered_block_ids):
            missing = current - proposed
            extra = proposed - current
            raise ValueError(
                "reorder_blocks requires the full block set as a permutation. "
                f"missing_from_input={sorted(missing)!r} "
                f"unknown_block_ids={sorted(extra)!r}"
            )
        if current_list == ordered_block_ids:
            return
        _apply_block_order(con, authority, ordered_block_ids)
        _refresh_content_state(con, authority, bump_revision=True)


def get_notebook(con: Any, authority: NotebookAuthority) -> Notebook | None:
    """Read a notebook + ordered blocks. Returns None if not found.

    **Does not resolve substrate references**; the caller (or a render
    helper) resolves block.ref_id against substrate.graph for the
    live state. This keeps the substrate-source-of-truth invariant
    explicit (§13.2)."""
    authority = _require_authority(authority)
    row = con.execute(
        """
        SELECT notebook_id, title, investigation_id, investigation_digest, document_id,
               owner_user_id, content_class, created_at, updated_at,
               metadata, schema_version, revision, content_sha256
        FROM notebooks WHERE account_digest = ? AND notebook_id = ?
        """,
        [authority.account_digest, authority.notebook_id],
    ).fetchone()
    if row is None:
        return None
    (
        nb_id,
        title,
        inv_id,
        inv_digest,
        doc_id,
        owner,
        cc,
        created,
        updated,
        md,
        schema_version,
        revision,
        content_sha256,
    ) = row
    if owner != authority.account_id:
        raise NotebookCorruptError("notebook ownership is unavailable")
    if inv_digest != _investigation_digest(authority, inv_id):
        raise NotebookCorruptError("notebook investigation authority is unavailable")
    metadata = _decode_json_object(md or "{}", field_name="metadata")

    block_rows = _block_rows(con, authority)
    blocks = []
    for b in block_rows:
        b_id, nb, idx, bt, rid, cj, b_created = b
        content = _decode_json_object(cj, field_name="block content")
        blocks.append(NotebookBlock(
            block_id=b_id, notebook_id=nb, block_index=idx,
            block_type=bt, ref_id=rid, content_json=content,
            created_at=str(b_created),
        ))

    document_hash = canonical_document_sha256(_document_from_block_rows(block_rows))
    if document_hash != content_sha256:
        raise NotebookCorruptError("notebook content hash is unavailable")
    return Notebook(
        notebook_id=nb_id, title=title,
        investigation_id=inv_id, document_id=doc_id,
        owner_user_id=owner, content_class=cc,
        schema_version=int(schema_version), revision=int(revision),
        content_sha256=str(content_sha256),
        created_at=str(created), updated_at=str(updated),
        metadata=metadata, blocks=blocks,
    )


def list_notebooks(
    con: Any,
    account: NotebookAccountAuthority,
    *,
    investigation_id: str | None = None,
    document_id: str | None = None,
    limit: int = 100,
) -> list[Notebook]:
    """List only one request-derived account's notebooks."""
    if not isinstance(account, NotebookAccountAuthority):
        raise TypeError("NotebookAccountAuthority is required")
    where_clauses = ["account_digest = ?"]
    params: list[Any] = [account.account_digest]
    if investigation_id is not None:
        where_clauses.append("investigation_id = ?")
        params.append(investigation_id)
        from substrate.investigation_tenancy import InvestigationAuthority

        where_clauses.append("investigation_digest = ?")
        params.append(
            InvestigationAuthority(account.account_id, investigation_id).investigation_digest
        )
    if document_id is not None:
        where_clauses.append("document_id = ?")
        params.append(document_id)
    sql = "SELECT notebook_id FROM notebooks WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(int(limit))

    ids = [r[0] for r in con.execute(sql, params).fetchall()]
    # Resolve each (with blocks) — N+1 but at Sprint 18 scale this is
    # fine; bulk fetch lands when notebook count gets meaningful.
    return [
        notebook
        for notebook_id in ids
        if (notebook := get_notebook(con, account.notebook(str(notebook_id))))
    ]


def _request_sha256(
    *,
    schema_version: int,
    base_revision: int,
    mutation_key: str,
    doc: dict[str, Any],
) -> str:
    return canonical_document_sha256(
        {
            "schema_version": schema_version,
            "base_revision": base_revision,
            "mutation_key": mutation_key,
            "doc": doc,
        }
    )


def replace_document(
    con: Any,
    authority: NotebookAuthority,
    *,
    schema_version: int,
    base_revision: int,
    mutation_key: str,
    doc: dict[str, Any],
) -> NotebookMutationReceipt:
    """Conditionally replace a full TipTap document with immutable replay."""

    from .tiptap_codec import decompose, is_effectively_empty

    authority = _require_authority(authority)
    if schema_version != 1:
        raise ValueError("schema_version must be 1")
    if not isinstance(base_revision, int) or base_revision < 0:
        raise ValueError("base_revision must be a non-negative integer")
    if (
        not isinstance(mutation_key, str)
        or not mutation_key
        or mutation_key != mutation_key.strip()
        or len(mutation_key.encode("utf-8")) > 200
    ):
        raise ValueError("mutation_key is invalid")
    decomposed = decompose(doc)
    incoming_hash = canonical_document_sha256(doc)
    request_sha256 = _request_sha256(
        schema_version=schema_version,
        base_revision=base_revision,
        mutation_key=mutation_key,
        doc=doc,
    )
    with _mutation(con):
        current = con.execute(
            "SELECT revision, content_sha256 FROM notebooks "
            "WHERE account_digest = ? AND notebook_id = ?",
            [authority.account_digest, authority.notebook_id],
        ).fetchone()
        if current is None:
            raise NotebookNotFoundError("notebook not found")
        current_revision, current_hash = int(current[0]), str(current[1])
        replay = con.execute(
            "SELECT request_sha256, revision, content_sha256 "
            "FROM notebook_mutation_receipts WHERE account_digest = ? "
            "AND notebook_id = ? AND mutation_key = ?",
            [authority.account_digest, authority.notebook_id, mutation_key],
        ).fetchone()
        if replay is not None:
            if str(replay[0]) != request_sha256:
                raise NotebookMutationConflict(
                    "mutation_key_reused",
                    revision=current_revision,
                    content_sha256=current_hash,
                )
            return NotebookMutationReceipt(
                schema_version=1,
                notebook_id=authority.notebook_id,
                revision=int(replay[1]),
                content_sha256=str(replay[2]),
                replayed=True,
            )
        existing = get_notebook(con, authority)
        if existing is None:
            raise NotebookNotFoundError("notebook not found")
        if base_revision != existing.revision:
            raise NotebookMutationConflict(
                "stale_revision",
                revision=existing.revision,
                content_sha256=existing.content_sha256,
            )
        if is_effectively_empty(doc) and existing.blocks:
            raise NotebookEmptyDocumentConflict(
                revision=existing.revision,
                content_sha256=existing.content_sha256,
                existing_block_count=len(existing.blocks),
            )
        if incoming_hash == existing.content_sha256:
            next_revision = existing.revision
        else:
            con.execute(
                "DELETE FROM notebook_blocks WHERE account_digest = ? "
                "AND notebook_id = ?",
                [authority.account_digest, authority.notebook_id],
            )
            for index, block in enumerate(decomposed):
                con.execute(
                    "INSERT INTO notebook_blocks (account_digest, block_id, notebook_id, "
                    "block_index, block_type, ref_id, content_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        authority.account_digest,
                        f"nbb-{uuid.uuid4().hex[:12]}",
                        authority.notebook_id,
                        index,
                        block.block_type,
                        block.ref_id,
                        json.dumps(block.content_json),
                    ],
                )
            next_revision = existing.revision + 1
            con.execute(
                "UPDATE notebooks SET revision = ?, content_sha256 = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE account_digest = ? "
                "AND notebook_id = ?",
                [
                    next_revision,
                    incoming_hash,
                    authority.account_digest,
                    authority.notebook_id,
                ],
            )
        con.execute(
            "INSERT INTO notebook_mutation_receipts (account_digest, notebook_id, "
            "mutation_key, request_sha256, revision, content_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                authority.account_digest,
                authority.notebook_id,
                mutation_key,
                request_sha256,
                next_revision,
                incoming_hash,
            ],
        )
        return NotebookMutationReceipt(
            schema_version=1,
            notebook_id=authority.notebook_id,
            revision=next_revision,
            content_sha256=incoming_hash,
            replayed=False,
        )


def append_document_block(
    con: Any,
    authority: NotebookAuthority,
    *,
    schema_version: int,
    base_revision: int,
    mutation_key: str,
    block: dict[str, Any],
) -> NotebookMutationReceipt:
    """Atomically append one TipTap block under account-qualified OCC."""

    from .tiptap_codec import decompose

    authority = _require_authority(authority)
    if schema_version != 1:
        raise ValueError("schema_version must be 1")
    if not isinstance(base_revision, int) or base_revision < 0:
        raise ValueError("base_revision must be a non-negative integer")
    if (
        not isinstance(mutation_key, str)
        or not mutation_key
        or mutation_key != mutation_key.strip()
        or len(mutation_key.encode("utf-8")) > 200
    ):
        raise ValueError("mutation_key is invalid")
    decomposed = decompose({"type": "doc", "content": [block]})
    if len(decomposed) != 1:
        raise ValueError("exactly one TipTap block is required")
    item = decomposed[0]
    request_sha256 = canonical_document_sha256(
        {
            "command": "append_document_block_v1",
            "schema_version": schema_version,
            "base_revision": base_revision,
            "mutation_key": mutation_key,
            "block": block,
        }
    )
    with _mutation(con):
        current = get_notebook(con, authority)
        if current is None:
            raise NotebookNotFoundError("notebook not found")
        replay = con.execute(
            "SELECT request_sha256, revision, content_sha256 "
            "FROM notebook_mutation_receipts WHERE account_digest = ? "
            "AND notebook_id = ? AND mutation_key = ?",
            [authority.account_digest, authority.notebook_id, mutation_key],
        ).fetchone()
        if replay is not None:
            if str(replay[0]) != request_sha256:
                raise NotebookMutationConflict(
                    "mutation_key_reused",
                    revision=current.revision,
                    content_sha256=current.content_sha256,
                )
            return NotebookMutationReceipt(
                schema_version=1,
                notebook_id=authority.notebook_id,
                revision=int(replay[1]),
                content_sha256=str(replay[2]),
                replayed=True,
            )
        if base_revision != current.revision:
            raise NotebookMutationConflict(
                "stale_revision",
                revision=current.revision,
                content_sha256=current.content_sha256,
            )
        next_index = len(current.blocks)
        con.execute(
            "INSERT INTO notebook_blocks (account_digest, block_id, notebook_id, "
            "block_index, block_type, ref_id, content_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                authority.account_digest,
                f"nbb-{uuid.uuid4().hex[:12]}",
                authority.notebook_id,
                next_index,
                item.block_type,
                item.ref_id,
                json.dumps(item.content_json),
            ],
        )
        _refresh_content_state(con, authority, bump_revision=True)
        updated = get_notebook(con, authority)
        if updated is None:  # pragma: no cover - transaction invariant
            raise NotebookCorruptError("notebook append disappeared")
        con.execute(
            "INSERT INTO notebook_mutation_receipts (account_digest, notebook_id, "
            "mutation_key, request_sha256, revision, content_sha256) VALUES (?, ?, ?, ?, ?, ?)",
            [
                authority.account_digest,
                authority.notebook_id,
                mutation_key,
                request_sha256,
                updated.revision,
                updated.content_sha256,
            ],
        )
        return NotebookMutationReceipt(
            schema_version=1,
            notebook_id=authority.notebook_id,
            revision=updated.revision,
            content_sha256=updated.content_sha256,
            replayed=False,
        )


def restore_block(
    con: Any,
    authority: NotebookAuthority,
    block_id: str,
    *,
    block_index: int,
    block_type: str,
    ref_id: str | None,
    content: dict[str, Any],
) -> None:
    """Owner-qualified inverse seam for the existing AI undo path."""

    authority = _require_authority(authority)
    if block_type not in VALID_BLOCK_TYPES:
        raise ValueError("block_type is invalid")
    with _mutation(con):
        notebook = con.execute(
            "SELECT 1 FROM notebooks WHERE account_digest = ? AND notebook_id = ?",
            [authority.account_digest, authority.notebook_id],
        ).fetchone()
        if notebook is None:
            raise NotebookNotFoundError("notebook not found")
        existing_rows = con.execute(
            "SELECT block_id FROM notebook_blocks WHERE account_digest = ? "
            "AND notebook_id = ? ORDER BY block_index",
            [authority.account_digest, authority.notebook_id],
        ).fetchall()
        ordered_ids = [str(row[0]) for row in existing_rows]
        if block_id in ordered_ids:
            current = con.execute(
                "SELECT block_index, block_type, ref_id, content_json "
                "FROM notebook_blocks WHERE account_digest = ? AND notebook_id = ? "
                "AND block_id = ?",
                [authority.account_digest, authority.notebook_id, block_id],
            ).fetchone()
            if current is None:
                raise NotebookStorageError("notebook block disappeared during restore")
            desired_index = min(max(int(block_index), 0), len(ordered_ids) - 1)
            current_content = _decode_json_object(current[3], field_name="block content")
            if (
                int(current[0]) == desired_index
                and str(current[1]) == block_type
                and current[2] == ref_id
                and current_content == content
            ):
                return
            con.execute(
                "UPDATE notebook_blocks SET block_type = ?, ref_id = ?, content_json = ? "
                "WHERE account_digest = ? AND notebook_id = ? AND block_id = ?",
                [
                    block_type,
                    ref_id,
                    json.dumps(content),
                    authority.account_digest,
                    authority.notebook_id,
                    block_id,
                ],
            )
            if int(current[0]) != desired_index:
                ordered_ids.remove(block_id)
                ordered_ids.insert(desired_index, block_id)
                _apply_block_order(con, authority, ordered_ids)
        else:
            con.execute(
                "INSERT INTO notebook_blocks (account_digest, block_id, notebook_id, "
                "block_index, block_type, ref_id, content_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    authority.account_digest,
                    block_id,
                    authority.notebook_id,
                    len(ordered_ids),
                    block_type,
                    ref_id,
                    json.dumps(content),
                ],
            )
            insert_at = min(max(int(block_index), 0), len(ordered_ids))
            ordered_ids.insert(insert_at, block_id)
            _apply_block_order(con, authority, ordered_ids)
        _refresh_content_state(con, authority, bump_revision=True)


def restore_notebook_metadata(
    con: Any,
    authority: NotebookAuthority,
    *,
    title: str | None,
    content_class: str | None,
) -> None:
    authority = _require_authority(authority)
    if content_class is not None and content_class not in VALID_NOTEBOOK_CONTENT_CLASSES:
        raise ValueError("content_class is invalid")
    with _mutation(con):
        row = con.execute(
            "SELECT title, content_class FROM notebooks WHERE account_digest = ? "
            "AND notebook_id = ?",
            [authority.account_digest, authority.notebook_id],
        ).fetchone()
        if row is None:
            raise NotebookNotFoundError("notebook not found")
        next_title = row[0] if title is None else title
        next_class = row[1] if content_class is None else content_class
        if (next_title, next_class) == row:
            return
        con.execute(
            "UPDATE notebooks SET title = ?, content_class = ? WHERE account_digest = ? "
            "AND notebook_id = ?",
            [next_title, next_class, authority.account_digest, authority.notebook_id],
        )
        _refresh_content_state(con, authority, bump_revision=True)


@dataclass(frozen=True)
class QualityGateInputs:
    """Inputs derived from a Notebook for the §13.9 quality-gate
    evaluator. ``rubric_score`` is left as a caller-supplied scalar
    because Sprint 19 hasn't bound a deterministic rubric scorer to
    notebook blocks yet — operator-driven promotion runs the gate
    with the operator's own rubric verdict."""

    text_content: str
    cited_chunk_tiers: list[int]
    corpus_sector_terms: list[str]


def gather_quality_gate_inputs(con: Any, notebook: Notebook) -> QualityGateInputs:
    """Walk a notebook's blocks to derive the quality-gate inputs:

      - text_content: concatenated prose from every ``prose`` block
        (joined with blank lines so paragraph density survives).
      - cited_chunk_tiers: source_tier values for every chunk
        referenced by ``region_embed``, ``claim_card``, or
        ``cross_doc_link`` blocks. Chunks resolve to documents via
        the existing FK; missing FKs default to tier 4 (general).

    Per master-spec §13.9: this helper is the single, testable
    derivation step between notebook state and the quality-gate
    evaluator. Future iterations add corpus_sector_terms from the
    investigation's parameters; Sprint 19 leaves it empty.
    """
    prose_chunks: list[str] = []
    referenced_chunk_ids: list[str] = []
    for block in notebook.blocks:
        if block.block_type == "prose":
            text = (block.content_json or {}).get("text", "")
            if isinstance(text, str) and text.strip():
                prose_chunks.append(text)
        elif block.block_type in {"region_embed", "claim_card", "cross_doc_link"}:
            ref_id = block.ref_id
            if ref_id:
                referenced_chunk_ids.append(ref_id)

    text_content = "\n\n".join(prose_chunks)

    cited_chunk_tiers: list[int] = []
    if referenced_chunk_ids:
        if (
            os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1"
            and notebook.investigation_id
        ):
            from substrate.investigation_tenancy import InvestigationAuthority
            from substrate.legal_gate.policy_store import LegalPolicyDenied
            from substrate.legal_gate.read import read_chunk, read_document

            authority = InvestigationAuthority(
                notebook.owner_user_id, notebook.investigation_id
            )
            for chunk_id in referenced_chunk_ids:
                try:
                    chunk = read_chunk(con, authority, chunk_id)
                    document = read_document(con, authority, chunk["document_id"])
                except LegalPolicyDenied:
                    continue
                cited_chunk_tiers.append(int(document["source_tier"]))
        elif os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") != "1":
            from substrate.legal_gate.read import legacy_notebook_chunk_tiers

            cited_chunk_tiers = legacy_notebook_chunk_tiers(
                con, referenced_chunk_ids
            )
        # Backfill: any referenced chunk that didn't resolve gets tier 4.
        missing = len(referenced_chunk_ids) - len(cited_chunk_tiers)
        if missing > 0:
            cited_chunk_tiers.extend([4] * missing)

    return QualityGateInputs(
        text_content=text_content,
        cited_chunk_tiers=cited_chunk_tiers,
        corpus_sector_terms=[],
    )


def promote_to_public(con: Any, authority: NotebookAuthority) -> None:
    """Operator promotes a user_owned notebook to
    user_public_contribution. Per master-spec §13.9 quality gate: the
    promotion path is where verification + voice-style scoring +
    source-tier validation runs.

    For Sprint 18 the substrate just records the state transition;
    the quality gate runs at the API-layer endpoint that wraps this
    function (see interfaces/research/api/app.py
    POST /notebooks/{id}/promote-public)."""
    authority = _require_authority(authority)
    with _mutation(con):
        row = con.execute(
            "SELECT content_class FROM notebooks WHERE account_digest = ? "
            "AND notebook_id = ?",
            [authority.account_digest, authority.notebook_id],
        ).fetchone()
        if row is None:
            raise NotebookNotFoundError("notebook not found")
        if row[0] == "user_public_contribution":
            return
        con.execute(
            "UPDATE notebooks SET content_class = 'user_public_contribution' "
            "WHERE account_digest = ? AND notebook_id = ? "
            "AND content_class = 'user_owned'",
            [authority.account_digest, authority.notebook_id],
        )
        _refresh_content_state(con, authority, bump_revision=True)


__all__ = [
    "Notebook",
    "NotebookAlreadyExists",
    "NotebookBlock",
    "NotebookCorruptError",
    "NotebookEmptyDocumentConflict",
    "NotebookMutationConflict",
    "NotebookMutationReceipt",
    "NotebookNotFoundError",
    "NotebookStorageError",
    "QualityGateInputs",
    "VALID_BLOCK_TYPES",
    "VALID_NOTEBOOK_CONTENT_CLASSES",
    "append_block",
    "append_document_block",
    "create_notebook",
    "delete_block",
    "gather_quality_gate_inputs",
    "get_notebook",
    "list_notebooks",
    "promote_to_public",
    "reorder_blocks",
    "replace_document",
    "restore_block",
    "restore_notebook_metadata",
    "update_block",
]
