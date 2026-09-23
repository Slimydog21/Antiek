"""Resolve graph node ref_ids and synthesis-manifest pins to their sources (HPRJ).

Reads the live DuckDB graph via ``connect_read`` only. Reports source-document
``content_class`` / ``ip_holder_id`` faithfully; the notebook/deliverable/synthesis
adapters apply ``SERVABLE_CONTENT_CLASSES`` filtering — this module must not
pre-filter.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
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

# Node kinds that are DERIVED FROM SOURCES. One of these from which no source
# is reachable (no metadata pointer, and no supported_by edge that leads to
# one) is an unsupported claim, not the operator's own words: its rights are
# unknown and it resolves to the gated default. A question (the operator
# asked it) or any other kind keeps None — genuinely own content.
_SOURCED_KINDS: frozenset[str] = frozenset({"claim", "insight", "evidence"})

# The documents something stands on, one entry per grounding pointer. None is
# a pointer that cannot be followed (the chunk or row it names is gone): a
# source whose rights are unknown, never a missing source.
Grounding = list[str | None]

# How many edges deep one grounding walk follows (an edge leads to its
# endpoints, whose supported_by edges lead on). An edge past this is not read
# and counts as one unresolved source, so a pathologically deep chain
# withholds the text instead of reading an unbounded graph mid-export.
_MAX_EDGE_DEPTH = 64

# A graph row the walk expands: ("node", node_id) or ("edge", edge_id).
_Row = tuple[str, str]


@dataclass
class _Expansion:
    """What one graph row stands on directly: the documents it names
    (``names``) and the rows whose grounding it inherits (``rests_on``).
    ``sourced`` marks a node of a sourced kind, which must reach a source."""

    names: Grounding = field(default_factory=list)
    rests_on: list[_Row] = field(default_factory=list)
    sourced: bool = False


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


def _metadata_pointers(metadata_raw: object) -> list[tuple[str, str]] | None:
    """Every pointer recorded in a row's ``metadata``, or None when metadata
    is present but cannot be parsed.

    The pointers are found by ``collect_pointers`` from the shape of their
    keys, at any depth, never from a list of known fields: a writer that adds
    a new pointer field is read without a change here. Unparseable metadata
    may hold any pointer, so the caller counts it as one unresolved pointer
    rather than as none."""
    if metadata_raw is None or (isinstance(metadata_raw, str) and not metadata_raw.strip()):
        return []
    try:
        meta = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
    except (TypeError, ValueError):
        return None
    return list(collect_pointers(meta))


def _follow(con: Any, kind: str, ref: str, into: _Expansion) -> None:
    """Record what one pointer names on ``into``. A document names itself and
    a chunk its document; an edge or node is a row to expand. A ``source``
    pointer's key does not say what it names, so it is followed as whichever
    of a document, chunk or edge it is; a pointer that names none of them, or
    a kind outside these, cannot be followed and is unresolved."""
    if kind == "document":
        into.names.append(ref)
    elif kind == "chunk":
        into.names.append(_chunk_document(con, ref))
    elif kind in ("edge", "node"):
        into.rests_on.append((kind, ref))
    elif kind == "source" and _row_exists(con, "documents", "document_id", ref):
        into.names.append(ref)
    elif kind == "source" and _row_exists(con, "chunks", "chunk_id", ref):
        into.names.append(_chunk_document(con, ref))
    elif kind == "source" and _row_exists(con, "edges", "edge_id", ref):
        into.rests_on.append(("edge", ref))
    else:
        into.names.append(None)


def _follow_metadata(con: Any, metadata_raw: object, into: _Expansion) -> None:
    """Follow every pointer a row's ``metadata`` records; metadata that
    cannot be parsed is one unresolved pointer."""
    pointers = _metadata_pointers(metadata_raw)
    if pointers is None:
        into.names.append(None)
        return
    for kind, ref in pointers:
        _follow(con, kind, ref, into)


def _expand_node(con: Any, node_id: str) -> _Expansion:
    """A node stands on every pointer its metadata records, found by key
    shape at any depth (``source_document_id``, ``chunk_id``,
    ``source_chunk_ids`` and any pointer field a writer adds later), and on
    every ``supported_by`` edge out of it whichever investigation wrote it.
    Other relations do not establish grounding. A node whose row is gone is
    one unresolved pointer, since the text it held is unknown."""
    row = con.execute(
        "SELECT node_type, metadata FROM nodes WHERE node_id = ?", [node_id]
    ).fetchone()
    if row is None:
        return _Expansion(names=[None])
    out = _Expansion(sourced=str(row[0]) in _SOURCED_KINDS)
    _follow_metadata(con, row[1], out)
    for (edge_id,) in con.execute(
        "SELECT edge_id FROM edges "
        "WHERE source_node_id = ? AND relation = 'supported_by' ORDER BY edge_id",
        [node_id],
    ).fetchall():
        out.rests_on.append(("edge", str(edge_id)))
    return out


def _expand_edge(con: Any, edge_id: str) -> _Expansion:
    """An edge stands on its chunk's document, its own
    ``source_document_id``, every pointer in its metadata, and both endpoint
    nodes. An edge whose row is gone is one unresolved pointer."""
    row = con.execute(
        "SELECT chunk_id, source_document_id, metadata, source_node_id, "
        "target_node_id FROM edges WHERE edge_id = ?",
        [edge_id],
    ).fetchone()
    if row is None:
        return _Expansion(names=[None])
    chunk_id, document_id, metadata_raw, source_node, target_node = row
    out = _Expansion()
    if chunk_id is not None:
        out.names.append(_chunk_document(con, str(chunk_id)))
    if document_id is not None:
        out.names.append(str(document_id))
    _follow_metadata(con, metadata_raw, out)
    for endpoint in (source_node, target_node):
        if endpoint is not None:
            out.rests_on.append(("node", str(endpoint)))
    return out


def _grounding(con: Any, kind: str, ref: str) -> Grounding:
    """Every document one pointer stands on, in a stable order.

    The walk has two phases, because a row the walk has already reached is
    not a source. First it reads the whole dependency graph the pointer
    reaches: each node and edge once (the graph has cycles: edges name nodes,
    and node metadata can name edges), breadth first, recording what each
    row names and which rows it rests on. Then it decides grounding on the
    finished graph: a row is grounded when some named document, or some
    unresolved pointer, is reachable from it through the rows it rests on.

    The result is every document any reached row names, plus one unresolved
    source (None) for each sourced node that is not grounded: a claim whose
    only support is an edge to an entity that needs no source, or a cycle of
    claims supported only by each other, has rights nobody recorded. A cycle
    that reaches a public document anywhere is grounded from every row on it.
    An edge more than ``_MAX_EDGE_DEPTH`` edges from the pointer is not read
    and counts as one unresolved source."""
    start = _Expansion()
    _follow(con, kind, ref, start)
    graph: dict[_Row, _Expansion] = {}
    depth: dict[_Row, int] = {}
    queue: deque[_Row] = deque()
    for row in start.rests_on:
        if row not in depth:
            depth[row] = int(row[0] == "edge")
            queue.append(row)
    while queue:
        row = queue.popleft()
        if row[0] == "edge" and depth[row] > _MAX_EDGE_DEPTH:
            graph[row] = _Expansion(names=[None])
            continue
        graph[row] = expansion = (
            _expand_edge(con, row[1]) if row[0] == "edge" else _expand_node(con, row[1])
        )
        for nxt in expansion.rests_on:
            if nxt not in depth:
                depth[nxt] = depth[row] + int(nxt[0] == "edge")
                queue.append(nxt)

    # A row is grounded if it names a source or rests on a grounded row:
    # propagate from the rows that name something back along ``rests_on``.
    dependants: dict[_Row, list[_Row]] = {}
    for row, expansion in graph.items():
        for nxt in expansion.rests_on:
            dependants.setdefault(nxt, []).append(row)
    grounded = {row for row, expansion in graph.items() if expansion.names}
    frontier = list(grounded)
    while frontier:
        for row in dependants.get(frontier.pop(), []):
            if row not in grounded:
                grounded.add(row)
                frontier.append(row)

    docs: Grounding = list(start.names)
    for expansion in graph.values():
        docs.extend(expansion.names)
    docs.extend(
        None for row, expansion in graph.items()
        if expansion.sourced and row not in grounded
    )
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
                "SELECT node_id, canonical_label, node_type FROM nodes WHERE node_id = ?",
                [ref_id],
            ).fetchone()
            if row is None:
                continue

            node_id, canonical_label, node_type = row
            sources: list[tuple[str | None, str | None, str | None, str | None]] = []
            for doc_id in _grounding(con, "node", str(node_id)):
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
    cannot be followed (a pinned row that is gone, a kind outside the
    manifest CHECK list) comes back unresolved rather than omitted; a
    structural pin that is not a source (an entity node, or an edge that
    names nothing between nodes that need no source) is skipped. ``con`` is
    any read connection."""
    out: list[PinnedSource] = []
    for kind, entity_id in pins:
        kind, entity_id = str(kind), str(entity_id)
        for doc_id in _grounding(con, kind, entity_id):
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
