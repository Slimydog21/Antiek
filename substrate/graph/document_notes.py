"""DRW SPR-10 — notes anchored to a document, for the reading surface.

The reading surface renders a document already annotated with the insight +
open-question nodes SPR-03's always-on pass distilled from it. This module
answers "what notes belong to document X, and where do they anchor?".

The note→document linkage as SPR-03 actually writes it (verified against
``roles/note_taker/document_pass.run_document_pass``):

  * an **insight** node carries ``metadata.source_chunk_ids`` — the chunks it
    was distilled from;
  * a **question** node carries ``metadata.source_document_id`` — the doc.

**Anchoring model (the case that bites — rigor #3).** A note does NOT store a
fragile ``(start, end)`` offset into the document, because the document is
editable (SPR-08 versions ``raw_text``) and offsets rot the instant a span is
edited. Instead a note anchors to the **text of its source chunk(s)**: the
frontend locates that text in the (possibly edited) ``raw_text`` by content
match. If the text is still present → the highlight re-anchors automatically;
if an edit removed it → the anchor is marked *stale* (surfaced, never silently
pointed at the wrong span). Content-addressed anchoring degrades gracefully by
construction. This module therefore returns the **anchor text**, not offsets.

The match is **whitespace-normalized** (collapse runs of whitespace before
comparing): chunks are paragraph-joined, so a chunk's text is not a verbatim
byte-substring of ``raw_text`` even before any edit, and a human edit reflows
whitespace constantly. Normalized matching is robust to both; the frontend
normalizes ``raw_text`` + the anchor identically, finds the anchor, and maps
back to the original offsets to draw the highlight.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, List

try:
    from ...runtime.db_lock import connect_read
    from .insight_question import graph_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_read  # type: ignore[no-redef]
    from substrate.graph.insight_question import graph_db_path  # type: ignore[no-redef]


@dataclass(frozen=True)
class DocumentNote:
    node_id: str
    kind: str               # "insight" | "question"
    text: str               # the living note text (canonical_label)
    confidence: str
    anchors: tuple          # source chunk texts to locate in raw_text (content anchoring)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id, "kind": self.kind, "text": self.text,
            "confidence": self.confidence, "anchors": list(self.anchors),
        }


def _meta(raw) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def notes_for_document(con: Any, document_id: str) -> List[DocumentNote]:
    """Return the insight/question notes anchored to ``document_id``, each
    with its source-chunk anchor text. Ordered by node_id for determinism."""
    chunk_rows = con.execute(
        "SELECT chunk_id, text FROM chunks WHERE document_id = ?", [document_id]
    ).fetchall()
    chunk_text_by_id = {r[0]: r[1] for r in chunk_rows}
    chunk_ids = set(chunk_text_by_id)

    # Pre-filter on metadata mentioning the doc (questions) or one of its
    # chunks (insights) so we don't scan the whole node table. Refined in
    # Python against the parsed metadata.
    like_terms = [f'%"{document_id}"%'] + [f'%"{c}"%' for c in chunk_ids]
    where = " OR ".join("metadata LIKE ?" for _ in like_terms)
    sql = (
        "SELECT node_id, node_type, canonical_label, metadata FROM nodes "
        "WHERE node_type IN ('insight', 'question')"
    )
    params: list[Any] = []
    if where:
        sql += f" AND ({where})"
        params = like_terms
    sql += " ORDER BY node_id"
    rows = con.execute(sql, params).fetchall()

    out: List[DocumentNote] = []
    for node_id, node_type, label, metadata_json in rows:
        meta = _meta(metadata_json)
        source_chunk_ids = [c for c in (meta.get("source_chunk_ids") or []) if c in chunk_ids]
        belongs = bool(source_chunk_ids) or meta.get("source_document_id") == document_id
        if not belongs:
            continue
        anchors = tuple(chunk_text_by_id[c] for c in source_chunk_ids)
        out.append(DocumentNote(
            node_id=node_id, kind=node_type, text=label,
            confidence=meta.get("confidence", "unknown"), anchors=anchors,
        ))
    return out


def document_chunk_node_ids(con: Any, document_id: str) -> set:
    """The set of insight/question node ids anchored to a document — the
    scope key for surfacing document-relevant structural gaps (SPR-07)."""
    return {n.node_id for n in notes_for_document(con, document_id)}
