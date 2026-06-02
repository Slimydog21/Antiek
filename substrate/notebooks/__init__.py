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

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import Any, Optional

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
    created_at: str
    updated_at: str
    metadata: dict = field(default_factory=dict)
    blocks: list[NotebookBlock] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_notebook(
    con: Any,
    *,
    title: str,
    investigation_id: str | None = None,
    document_id: str | None = None,
    owner_user_id: str = "__operator__",
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
    notebook_id = f"nb-{uuid.uuid4().hex[:12]}"
    metadata_json = json.dumps(metadata or {})
    con.execute(
        """
        INSERT INTO notebooks (
            notebook_id, title, investigation_id, document_id,
            owner_user_id, content_class, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            notebook_id, title, investigation_id, document_id,
            owner_user_id, content_class, metadata_json,
        ],
    )
    return notebook_id


def append_block(
    con: Any,
    notebook_id: str,
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
    block_id = f"nbb-{uuid.uuid4().hex[:12]}"
    # Find next block_index.
    row = con.execute(
        "SELECT COALESCE(MAX(block_index) + 1, 0) FROM notebook_blocks "
        "WHERE notebook_id = ?",
        [notebook_id],
    ).fetchone()
    next_index = int(row[0]) if row else 0
    con.execute(
        """
        INSERT INTO notebook_blocks (
            block_id, notebook_id, block_index, block_type, ref_id, content_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [block_id, notebook_id, next_index, block_type, ref_id, json.dumps(content)],
    )
    # Bump notebook updated_at.
    con.execute(
        "UPDATE notebooks SET updated_at = CURRENT_TIMESTAMP WHERE notebook_id = ?",
        [notebook_id],
    )
    return block_id


def update_block(
    con: Any,
    notebook_id: str,
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
    existing = con.execute(
        "SELECT block_id FROM notebook_blocks "
        "WHERE notebook_id = ? AND block_id = ?",
        [notebook_id, block_id],
    ).fetchone()
    if existing is None:
        return False
    updates: list[str] = []
    params: list[Any] = []
    if content is not None:
        updates.append("content_json = ?")
        params.append(json.dumps(content))
    if ref_id is not None:
        updates.append("ref_id = ?")
        params.append(ref_id)
    elif clear_ref_id:
        updates.append("ref_id = NULL")
    if not updates:
        return True  # no-op success
    sql = (
        "UPDATE notebook_blocks SET " + ", ".join(updates) +
        " WHERE notebook_id = ? AND block_id = ?"
    )
    params.extend([notebook_id, block_id])
    con.execute(sql, params)
    con.execute(
        "UPDATE notebooks SET updated_at = CURRENT_TIMESTAMP "
        "WHERE notebook_id = ?",
        [notebook_id],
    )
    return True


def delete_block(con: Any, notebook_id: str, block_id: str) -> bool:
    """Delete one block by ID. Re-numbers the remaining blocks so
    ``block_index`` stays a dense [0..n-1] sequence — the UI assumes
    no gaps. Returns True if the block was deleted, False if not
    found.

    Per master-spec §13.2 substrate-is-source-of-truth: deleting a
    block deletes the row, not just hides it. Any literate-analysis
    notebook that references the deleted block via substrate ref
    surfaces a tombstone at render time."""
    existing = con.execute(
        "SELECT block_index FROM notebook_blocks "
        "WHERE notebook_id = ? AND block_id = ?",
        [notebook_id, block_id],
    ).fetchone()
    if existing is None:
        return False
    con.execute(
        "DELETE FROM notebook_blocks "
        "WHERE notebook_id = ? AND block_id = ?",
        [notebook_id, block_id],
    )
    # Re-number remaining blocks to keep block_index contiguous.
    rows = con.execute(
        "SELECT block_id FROM notebook_blocks "
        "WHERE notebook_id = ? ORDER BY block_index",
        [notebook_id],
    ).fetchall()
    for new_idx, (b_id,) in enumerate(rows):
        con.execute(
            "UPDATE notebook_blocks SET block_index = ? "
            "WHERE notebook_id = ? AND block_id = ?",
            [new_idx, notebook_id, b_id],
        )
    con.execute(
        "UPDATE notebooks SET updated_at = CURRENT_TIMESTAMP "
        "WHERE notebook_id = ?",
        [notebook_id],
    )
    return True


def reorder_blocks(
    con: Any, notebook_id: str, *, ordered_block_ids: list[str],
) -> None:
    """Re-order a notebook's blocks by the supplied list. The list
    must be a complete permutation of the notebook's current block_ids
    — partial reorders are rejected to keep the contract simple.

    Raises ``ValueError`` if the supplied list doesn't exactly match
    the notebook's current block set."""
    current = {
        r[0] for r in con.execute(
            "SELECT block_id FROM notebook_blocks WHERE notebook_id = ?",
            [notebook_id],
        ).fetchall()
    }
    proposed = set(ordered_block_ids)
    if current != proposed:
        missing = current - proposed
        extra = proposed - current
        raise ValueError(
            "reorder_blocks requires the full block set as a permutation. "
            f"missing_from_input={sorted(missing)!r} "
            f"unknown_block_ids={sorted(extra)!r}"
        )
    # Use a two-pass approach to avoid PRIMARY KEY collisions when
    # blocks swap indexes: first park each block at a high negative
    # index unique to the call, then assign the final indexes.
    import uuid as _uuid

    sentinel_offset = -(int(_uuid.uuid4().int >> 96) & 0xFFFFFF) - 1
    for i, b_id in enumerate(ordered_block_ids):
        con.execute(
            "UPDATE notebook_blocks SET block_index = ? "
            "WHERE notebook_id = ? AND block_id = ?",
            [sentinel_offset - i, notebook_id, b_id],
        )
    for i, b_id in enumerate(ordered_block_ids):
        con.execute(
            "UPDATE notebook_blocks SET block_index = ? "
            "WHERE notebook_id = ? AND block_id = ?",
            [i, notebook_id, b_id],
        )
    con.execute(
        "UPDATE notebooks SET updated_at = CURRENT_TIMESTAMP "
        "WHERE notebook_id = ?",
        [notebook_id],
    )


def get_notebook(con: Any, notebook_id: str) -> Notebook | None:
    """Read a notebook + ordered blocks. Returns None if not found.

    **Does not resolve substrate references**; the caller (or a render
    helper) resolves block.ref_id against substrate.graph for the
    live state. This keeps the substrate-source-of-truth invariant
    explicit (§13.2)."""
    row = con.execute(
        """
        SELECT notebook_id, title, investigation_id, document_id,
               owner_user_id, content_class, created_at, updated_at,
               metadata
        FROM notebooks WHERE notebook_id = ?
        """,
        [notebook_id],
    ).fetchone()
    if row is None:
        return None
    (
        nb_id, title, inv_id, doc_id, owner, cc, created, updated, md,
    ) = row
    metadata = {}
    if md:
        try:
            metadata = json.loads(md)
        except (TypeError, ValueError):
            pass

    block_rows = con.execute(
        """
        SELECT block_id, notebook_id, block_index, block_type, ref_id,
               content_json, created_at
        FROM notebook_blocks WHERE notebook_id = ? ORDER BY block_index
        """,
        [notebook_id],
    ).fetchall()
    blocks = []
    for b in block_rows:
        b_id, nb, idx, bt, rid, cj, b_created = b
        try:
            content = json.loads(cj) if cj else {}
        except (TypeError, ValueError):
            content = {}
        blocks.append(NotebookBlock(
            block_id=b_id, notebook_id=nb, block_index=idx,
            block_type=bt, ref_id=rid, content_json=content,
            created_at=str(b_created),
        ))

    return Notebook(
        notebook_id=nb_id, title=title,
        investigation_id=inv_id, document_id=doc_id,
        owner_user_id=owner, content_class=cc,
        created_at=str(created), updated_at=str(updated),
        metadata=metadata, blocks=blocks,
    )


def list_notebooks(
    con: Any,
    *,
    owner_user_id: str | None = None,
    investigation_id: str | None = None,
    document_id: str | None = None,
    limit: int = 100,
) -> list[Notebook]:
    """List notebooks. Pass owner_user_id to scope to a single user
    (multi-user Sprint 22+); pass investigation_id or document_id to
    scope to a binding. Without filters: returns all notebooks the
    caller is privileged to see (substrate-level — the API layer
    enforces auth)."""
    where_clauses = []
    params: list[Any] = []
    if owner_user_id is not None:
        where_clauses.append("owner_user_id = ?")
        params.append(owner_user_id)
    if investigation_id is not None:
        where_clauses.append("investigation_id = ?")
        params.append(investigation_id)
    if document_id is not None:
        where_clauses.append("document_id = ?")
        params.append(document_id)
    sql = """
        SELECT notebook_id FROM notebooks
    """
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(int(limit))

    ids = [r[0] for r in con.execute(sql, params).fetchall()]
    # Resolve each (with blocks) — N+1 but at Sprint 18 scale this is
    # fine; bulk fetch lands when notebook count gets meaningful.
    return [nb for nb_id in ids if (nb := get_notebook(con, nb_id))]


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
        placeholders = ", ".join(["?"] * len(referenced_chunk_ids))
        rows = con.execute(
            f"""
            SELECT d.source_tier
            FROM chunks c
            JOIN documents d ON d.document_id = c.document_id
            WHERE c.chunk_id IN ({placeholders})
            """,
            referenced_chunk_ids,
        ).fetchall()
        cited_chunk_tiers = [int(r[0]) for r in rows]
        # Backfill: any referenced chunk that didn't resolve gets tier 4.
        missing = len(referenced_chunk_ids) - len(cited_chunk_tiers)
        if missing > 0:
            cited_chunk_tiers.extend([4] * missing)

    return QualityGateInputs(
        text_content=text_content,
        cited_chunk_tiers=cited_chunk_tiers,
        corpus_sector_terms=[],
    )


def promote_to_public(con: Any, notebook_id: str) -> None:
    """Operator promotes a user_owned notebook to
    user_public_contribution. Per master-spec §13.9 quality gate: the
    promotion path is where verification + voice-style scoring +
    source-tier validation runs.

    For Sprint 18 the substrate just records the state transition;
    the quality gate runs at the API-layer endpoint that wraps this
    function (see interfaces/research/api/app.py
    POST /notebooks/{id}/promote-public)."""
    con.execute(
        """
        UPDATE notebooks
        SET content_class = 'user_public_contribution',
            updated_at = CURRENT_TIMESTAMP
        WHERE notebook_id = ? AND content_class = 'user_owned'
        """,
        [notebook_id],
    )
