"""Resolve graph node ref_ids and synthesis-manifest pins to their sources (HPRJ).

Reads the live DuckDB graph via ``connect_read`` only. Reports source-document
``content_class`` / ``ip_holder_id`` faithfully; the notebook/deliverable/synthesis
adapters apply ``SERVABLE_CONTENT_CLASSES`` filtering — this module must not
pre-filter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import connect_read
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS, SERVABLE_CONTENT_CLASSES

from ..adapters.notebook import ResolvedRefData

_KIND_PAYLOAD_KEYS: dict[str, str] = {
    "claim": "statement",
    "question": "question",
    "insight": "statement",
}

# Node kinds that are DERIVED FROM SOURCES. One of these with no source
# document at all (no metadata pointer, no supported_by edge) is an
# unsupported claim, not the operator's own words: its rights are unknown
# and it resolves to the gated default. A question (the operator asked it)
# or any other kind keeps None — genuinely own content.
_SOURCED_KINDS: frozenset[str] = frozenset({"claim", "insight", "evidence"})


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _payload_for_kind(node_type: str, canonical_label: str) -> dict[str, str]:
    key = _KIND_PAYLOAD_KEYS.get(node_type, "body")
    return {key: canonical_label, "text": canonical_label}


def _source_document_id(
    con: Any, node_id: str, metadata_raw: str | None
) -> str | None:
    meta = _parse_metadata(metadata_raw)
    doc_id = meta.get("source_document_id")
    if doc_id is not None:
        return str(doc_id) if doc_id else None
    row = con.execute(
        "SELECT source_document_id FROM edges "
        "WHERE source_node_id = ? AND relation = 'supported_by' "
        "AND source_document_id IS NOT NULL "
        "LIMIT 1",
        [node_id],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _document_rights(
    con: Any, document_id: str
) -> tuple[str | None, str | None, str | None]:
    row = con.execute(
        "SELECT title, content_class, ip_holder_id FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    if row is None:
        # The node names a source document that is not there. Its rights are
        # UNKNOWN, which the rights chokepoint treats as the gated default —
        # never as None, which the deliverable adapter reads as "the
        # operator's own content" and exports in full.
        return None, GATED_DEFAULT_CONTENT_CLASS, None
    title, content_class, ip_holder_id = row
    if content_class is None:
        content_class = GATED_DEFAULT_CONTENT_CLASS
    return title, content_class, ip_holder_id


def resolve_refs(ref_ids: list[str], *, db_path: str) -> dict[str, ResolvedRefData]:
    """Resolve notebook/deliverable ref_ids against the substrate graph.

    Missing node_ids are omitted from the result (never fabricated)."""
    if not ref_ids:
        return {}

    out: dict[str, ResolvedRefData] = {}
    con = connect_read(db_path)
    try:
        for ref_id in ref_ids:
            row = con.execute(
                "SELECT node_id, canonical_label, node_type, metadata "
                "FROM nodes WHERE node_id = ?",
                [ref_id],
            ).fetchone()
            if row is None:
                continue

            node_id, canonical_label, node_type, metadata_raw = row
            source_doc_id = _source_document_id(con, node_id, metadata_raw)

            title: str | None = None
            content_class: str | None = None
            ip_holder_id: str | None = None
            if not source_doc_id and str(node_type) in _SOURCED_KINDS:
                content_class = GATED_DEFAULT_CONTENT_CLASS
            if source_doc_id:
                title, content_class, ip_holder_id = _document_rights(
                    con, source_doc_id
                )

            out[ref_id] = ResolvedRefData(
                kind=str(node_type),
                content_class=content_class,
                ip_holder_id=ip_holder_id,
                title=title,
                payload=_payload_for_kind(str(node_type), str(canonical_label)),
                source_document_id=source_doc_id,
            )
    finally:
        con.close()

    return out


@dataclass(frozen=True)
class PinnedSource:
    """The source document one synthesis-manifest pin stands on.

    ``document_id`` is None when the pin cannot be followed to a live document:
    the pinned row is gone, its grounding names a chunk or document that is
    gone, or it is a sourced node that names no source. Such a pin is
    unresolved, never dropped: its rights are unknown, and the provenance gate
    has to count it."""

    entity_kind: str
    entity_id: str
    document_id: str | None
    title: str | None = None
    content_class: str | None = None
    ip_holder_id: str | None = None

    @property
    def resolved(self) -> bool:
        return self.document_id is not None

    @property
    def servable(self) -> bool:
        return self.content_class in SERVABLE_CONTENT_CLASSES


# Manifest order: the kinds nearest the source first, then pin time.
_PIN_KIND_ORDER = (
    "CASE entity_kind WHEN 'document' THEN 0 WHEN 'chunk' THEN 1 "
    "WHEN 'node' THEN 2 WHEN 'edge' THEN 3 ELSE 4 END"
)


def _chunk_document(con: Any, chunk_id: str) -> str | None:
    row = con.execute(
        "SELECT document_id FROM chunks WHERE chunk_id = ?", [chunk_id]
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def _pin_grounding(con: Any, kind: str, entity_id: str) -> tuple[str, ...] | None:
    """The document ids a pin grounds on. None when the pinned row, or a row
    its grounding names, is gone. An empty tuple is a structural pin (an entity
    node, an edge with no chunk or document) that is not a source."""
    if kind == "document":
        return (entity_id,)
    if kind == "chunk":
        doc = _chunk_document(con, entity_id)
        return None if doc is None else (doc,)
    if kind == "edge":
        row = con.execute(
            "SELECT chunk_id, source_document_id FROM edges WHERE edge_id = ?",
            [entity_id],
        ).fetchone()
        if row is None:
            return None
        chunk_id, doc_id = row
        docs: list[str] = []
        if chunk_id is not None:
            chunk_doc = _chunk_document(con, str(chunk_id))
            if chunk_doc is None:
                return None
            docs.append(chunk_doc)
        if doc_id is not None and str(doc_id) not in docs:
            docs.append(str(doc_id))
        return tuple(docs)
    if kind == "node":
        row = con.execute(
            "SELECT node_type, metadata FROM nodes WHERE node_id = ?", [entity_id]
        ).fetchone()
        if row is None:
            return None
        doc = _source_document_id(con, entity_id, row[1])
        if doc is not None:
            return (doc,)
        # A sourced kind with no source is an unsupported claim, not structure.
        return None if str(row[0]) in _SOURCED_KINDS else ()
    return None  # an entity_kind outside the manifest CHECK list


def resolve_manifest_sources(con: Any, synthesis_ids: list[str]) -> list[PinnedSource]:
    """Every substrate-manifest pin of ``synthesis_ids`` (document, chunk,
    node and edge), in manifest order, through ``resolve_pin_sources``."""
    if not synthesis_ids:
        return []
    ph = ",".join("?" for _ in synthesis_ids)
    pins = con.execute(
        f"SELECT entity_kind, entity_id FROM synthesis_substrate_manifest "
        f"WHERE synthesis_id IN ({ph}) "
        f"ORDER BY {_PIN_KIND_ORDER}, pinned_at, entity_id",
        list(synthesis_ids),
    ).fetchall()
    return resolve_pin_sources(con, [(str(k), str(e)) for k, e in pins])


def resolve_pin_sources(con: Any, pins: list[tuple[str, str]]) -> list[PinnedSource]:
    """Follow each ``(entity_kind, entity_id)`` pin to the source documents it
    stands on, with each document's rights read faithfully. A pin that cannot
    be followed comes back unresolved rather than omitted; a structural pin
    that is not a source is skipped. ``con`` is any read connection."""
    out: list[PinnedSource] = []
    for kind, entity_id in pins:
        kind, entity_id = str(kind), str(entity_id)
        grounding = _pin_grounding(con, kind, entity_id)
        if grounding is None:
            out.append(PinnedSource(kind, entity_id, None))
            continue
        for doc_id in grounding:
            row = con.execute(
                "SELECT title, content_class, ip_holder_id FROM documents "
                "WHERE document_id = ?",
                [doc_id],
            ).fetchone()
            if row is None:
                out.append(PinnedSource(kind, entity_id, None))
            else:
                out.append(PinnedSource(kind, entity_id, doc_id, row[0], row[1], row[2]))
    return out
