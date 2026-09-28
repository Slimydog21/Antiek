"""The anchor-map chunk manifest (anchor-first SPR-03).

An ordered manifest of a served book's chunks — (chunk_id, section_path,
body_start, body_end, node_text_sha256) — so the reading surface can stamp
DOM nodes with chunk identity and feed the layout-map's BaseGeometry. It
carries ids, offsets, and hashes ONLY, never body text: the offsets point
INTO the served body the caller already lawfully holds; nothing about the
body crosses this module. body_start/body_end are scalars into the
unicode-nfc-v1 normalized served text (the same normalization the anchor
schema pins to), located sequentially (chunks are ordered, so each search
resumes after the previous match). A chunk that does not locate in the
served body — an HTML-preferred sidecar body whose markup broke the plain
run — is OMITTED, and `complete` reports it honestly rather than fabricating
offsets.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from substrate.books.highlights.schema import SqlExecutor
from substrate.feedback.domain import normalize_node_text


@dataclass(frozen=True, slots=True)
class AnchorMapChunk:
    chunk_id: str
    section_path: str | None
    body_start: int
    body_end: int
    node_text_sha256: str


@dataclass(frozen=True, slots=True)
class AnchorMap:
    document_id: str
    chunks: tuple[AnchorMapChunk, ...]
    """True when every chunk of the document located in the served body."""
    complete: bool


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_anchor_map(
    con: SqlExecutor,
    *,
    document_id: str,
    served_text: str,
) -> AnchorMap:
    """Locate each of the document's chunks in the served body text.

    `con` is read at the caller's discipline (the router holds the read
    connection). The served text is the gated body the endpoint lawfully
    serves — it is read for offsets, never returned."""
    rows = con.execute(
        "SELECT chunk_id, section_path, text FROM chunks WHERE document_id = ? "
        "ORDER BY chunk_index",
        [document_id],
    ).fetchall()
    served = normalize_node_text(served_text)
    chunks: list[AnchorMapChunk] = []
    omitted = 0
    cursor = 0
    for row in rows:
        normalized = normalize_node_text(str(row[2]))
        i = served.find(normalized, cursor)
        if i < 0:
            omitted += 1
            continue
        end = i + len(normalized)
        chunks.append(
            AnchorMapChunk(
                chunk_id=str(row[0]),
                section_path=None if row[1] is None else str(row[1]),
                body_start=i,
                body_end=end,
                node_text_sha256=_sha256(normalized),
            )
        )
        cursor = end
    return AnchorMap(
        document_id=document_id,
        chunks=tuple(chunks),
        complete=omitted == 0,
    )
