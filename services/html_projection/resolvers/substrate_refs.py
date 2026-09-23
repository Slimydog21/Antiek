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
from substrate.provenance.pointers import collect_pointers

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

# The documents something stands on, one entry per grounding pointer. None is
# a pointer that cannot be followed (the chunk or row it names is gone): a
# source whose rights are unknown, never a missing source.
Grounding = list[str | None]

# The (kind, id) rows one grounding walk has already followed. Edges name
# nodes and node metadata can name edges, so the walk stops at a row it has
# seen instead of cycling.
_Seen = set[tuple[str, str]]


def _payload_for_kind(node_type: str, canonical_label: str) -> dict[str, str]:
    key = _KIND_PAYLOAD_KEYS.get(node_type, "body")
    return {key: canonical_label, "text": canonical_label}


def _chunk_document(con: Any, chunk_id: str) -> str | None:
    row = con.execute(
        "SELECT document_id FROM chunks WHERE chunk_id = ?", [chunk_id]
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def _row_exists(con: Any, table: str, column: str, value: str) -> bool:
    return (
        con.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", [value]).fetchone()
        is not None
    )


def _metadata_grounding(con: Any, metadata_raw: object, seen: _Seen) -> Grounding:
    """The documents every pointer recorded in a row's ``metadata`` names.

    The pointers are found by ``collect_pointers`` from the shape of their
    keys, at any depth, never from a list of known fields: a writer that adds
    a new pointer field is read without a change here. Metadata that is
    present but cannot be parsed may hold any pointer, so it is one
    unresolved pointer rather than none."""
    if metadata_raw is None or (isinstance(metadata_raw, str) and not metadata_raw.strip()):
        return []
    try:
        meta = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
    except (TypeError, ValueError):
        return [None]
    docs: Grounding = []
    for kind, ref in collect_pointers(meta):
        docs.extend(_pointer_grounding(con, kind, ref, seen))
    return docs


def _edge_grounding(con: Any, edge_id: str, seen: _Seen) -> Grounding:
    """The documents an edge stands on: its chunk's document, its own
    ``source_document_id``, every pointer in its metadata, and every pointer
    its two endpoint nodes record in their metadata. An edge row that is gone
    is one unresolved pointer; an edge that names nothing is structural
    (``[]``)."""
    row = con.execute(
        "SELECT chunk_id, source_document_id, metadata, source_node_id, "
        "target_node_id FROM edges WHERE edge_id = ?",
        [edge_id],
    ).fetchone()
    if row is None:
        return [None]
    chunk_id, document_id, metadata_raw, source_node, target_node = row
    docs: Grounding = []
    if chunk_id is not None:
        docs.append(_chunk_document(con, str(chunk_id)))
    if document_id is not None:
        docs.append(str(document_id))
    docs.extend(_metadata_grounding(con, metadata_raw, seen))
    for endpoint in (source_node, target_node):
        if endpoint is None or ("node", str(endpoint)) in seen:
            continue
        seen.add(("node", str(endpoint)))
        meta_row = con.execute(
            "SELECT metadata FROM nodes WHERE node_id = ?", [str(endpoint)]
        ).fetchone()
        if meta_row is not None:
            docs.extend(_metadata_grounding(con, meta_row[0], seen))
    return list(dict.fromkeys(docs))


def _pointer_grounding(
    con: Any, kind: str, ref: str, seen: _Seen
) -> Grounding:
    """The documents one recorded pointer names. A chunk resolves to its
    document, an edge through ``_edge_grounding``, a document to itself. A
    ``source`` pointer's key does not say what it names, so it is followed as
    whichever of a document, chunk or edge it is; one that names none of them
    cannot be followed and is unresolved. A pointer already followed on this
    walk adds nothing again (edges and nodes can point at each other)."""
    key = (kind, ref)
    if key in seen:
        return []
    seen.add(key)
    if kind == "document":
        return [ref]
    if kind == "chunk":
        return [_chunk_document(con, ref)]
    if kind == "edge":
        return _edge_grounding(con, ref, seen)
    if kind == "source":
        if _row_exists(con, "documents", "document_id", ref):
            return [ref]
        if _row_exists(con, "chunks", "chunk_id", ref):
            return [_chunk_document(con, ref)]
        if _row_exists(con, "edges", "edge_id", ref):
            return _edge_grounding(con, ref, seen)
    return [None]


def _node_grounding(
    con: Any,
    node_id: str,
    node_type: str,
    metadata_raw: str | None,
    seen: _Seen | None = None,
) -> Grounding:
    """Every document a node stands on, in a stable order.

    A node can carry several grounding pointers at once and its prose can
    repeat any of them, so all are read: every pointer its metadata records,
    found by key shape at any depth (``source_document_id``, ``chunk_id``,
    ``source_chunk_ids`` and any pointer field a writer adds later), and every
    ``supported_by`` edge out of the node whichever investigation wrote it,
    through ``_edge_grounding``. Other relations do not establish grounding.
    A sourced kind with no pointer at all is an unsupported claim whose
    rights are unknown (``[None]``); any other kind with no pointer is the
    operator's own content (``[]``)."""
    seen = set() if seen is None else seen
    seen.add(("node", node_id))
    docs: Grounding = _metadata_grounding(con, metadata_raw, seen)
    for (edge_id,) in con.execute(
        "SELECT edge_id FROM edges "
        "WHERE source_node_id = ? AND relation = 'supported_by' "
        "ORDER BY edge_id",
        [node_id],
    ).fetchall():
        docs.extend(_pointer_grounding(con, "edge", str(edge_id), seen))
    if not docs and str(node_type) in _SOURCED_KINDS:
        return [None]
    return list(dict.fromkeys(docs))


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

    A node standing on several sources reports the one that binds its rights:
    the first source that is unresolved or not servable, else the first
    source. That is a faithful report of the most restrictive source, not a
    filter; the adapters still decide what to embed.

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
            sources: list[tuple[str | None, str | None, str | None, str | None]] = []
            for doc_id in _node_grounding(con, node_id, str(node_type), metadata_raw):
                if doc_id is None:
                    sources.append((None, None, GATED_DEFAULT_CONTENT_CLASS, None))
                else:
                    sources.append((doc_id, *_document_rights(con, doc_id)))
            source_doc_id, title, content_class, ip_holder_id = next(
                (s for s in sources if s[2] not in SERVABLE_CONTENT_CLASSES),
                sources[0] if sources else (None, None, None, None),
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


def _pin_grounding(con: Any, kind: str, entity_id: str) -> Grounding:
    """The documents a pin grounds on, one entry per grounding pointer. A
    pinned row that is gone is one unresolved pointer. An empty list is a
    structural pin (an entity node, or an edge that names no chunk, document
    or pointer) that is not a source. A document, chunk, edge or ``source``
    pin (the kinds ``collect_pointers`` reports) resolves through
    ``_pointer_grounding``; a node through ``_node_grounding``."""
    if kind == "node":
        row = con.execute(
            "SELECT node_type, metadata FROM nodes WHERE node_id = ?", [entity_id]
        ).fetchone()
        if row is None:
            return [None]
        return _node_grounding(con, entity_id, str(row[0]), row[1])
    if kind in ("document", "chunk", "edge", "source"):
        return list(dict.fromkeys(_pointer_grounding(con, kind, entity_id, set())))
    return [None]  # an entity_kind outside the manifest CHECK list


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


def resolve_synthesis_sources(con: Any, synthesis_ids: list[str]) -> list[PinnedSource]:
    """What each recorded synthesis stands on, for clearing prose written
    from it. Each synthesis resolves through ``resolve_manifest_sources``, but
    one whose provenance cannot be traced at all (its row is gone, or its
    manifest pins no source) comes back as one unresolved ``synthesis``
    source rather than as nothing. Returning nothing would let the caller's
    other, public sources clear a thesis whose own sources are unknown."""
    out: list[PinnedSource] = []
    for sid in dict.fromkeys(str(s) for s in synthesis_ids):
        exists = con.execute(
            "SELECT 1 FROM syntheses WHERE synthesis_id = ?", [sid]
        ).fetchone()
        pinned = resolve_manifest_sources(con, [sid]) if exists else []
        out.extend(pinned or [PinnedSource("synthesis", sid, None)])
    return out


def resolve_pin_sources(con: Any, pins: list[tuple[str, str]]) -> list[PinnedSource]:
    """Follow each ``(entity_kind, entity_id)`` pin to every source document
    it stands on, with each document's rights read faithfully. A pin is a
    manifest kind (document, chunk, node, edge) or any pointer
    ``collect_pointers`` found in a recorded value. A grounding pointer that
    cannot be followed comes back unresolved rather than omitted; a
    structural pin that is not a source is skipped. ``con`` is any read
    connection."""
    out: list[PinnedSource] = []
    for kind, entity_id in pins:
        kind, entity_id = str(kind), str(entity_id)
        for doc_id in _pin_grounding(con, kind, entity_id):
            row = None
            if doc_id is not None:
                row = con.execute(
                    "SELECT title, content_class, ip_holder_id FROM documents "
                    "WHERE document_id = ?",
                    [doc_id],
                ).fetchone()
            if doc_id is None or row is None:
                out.append(PinnedSource(kind, entity_id, None))
            else:
                out.append(PinnedSource(kind, entity_id, doc_id, row[0], row[1], row[2]))
    return out
