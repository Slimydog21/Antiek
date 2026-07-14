"""Resolve a deliverable's §9.0-gated source-document titles for export.

GPW SPR-04 STRETCH. A deliverable's exported / sellable artifact should
carry a human-readable **Sources** list — the titles of the documents
that ultimately ground its prose. The substrate already stores the raw
provenance (``deliverable_sections.prose_provenance`` — a
``paragraph_index -> [block_id]`` map whose block_ids are graph node ids
attached via ``section_blocks``), and GPW SPR-04's floor (#196) surfaced
that raw map in the JSON export. But nothing resolved those ids to
source-document **titles** a reader can act on, so the Markdown / HTML /
Substack exports carried no Sources section at all.

This module does exactly that, and nothing more surfacing-sensitive:

* It emits document **titles only** — never bodies, never node labels.
* It drops any source whose resolved document ``content_class`` is
  withheld from a non-privileged (public / attribution-eligible) surface,
  reusing the public canonical ``is_chunk_body_withheld`` policy predicate
  from ``substrate/graph/retrieval_gate.py`` so the surfaces cannot drift
  apart (master-spec §9.0). A withheld source is therefore
  **indistinguishable from no source at all** — the required §9.0
  posture: an export must not even hint that a ``personal_reading``
  document exists.

Why titles are §9.0-safe here where node labels were not: a node
``canonical_label`` is free text that can leak a ``personal_reading``
body verbatim — GPW SPR-03 stayed correctly BLOCKED on exactly that
(the ungated node-label read, substrate gap #201). A document **title**
is surfaced only after gating on the resolved document's own
``content_class``, exactly as attribution does — so only
attribution-eligible documents are ever named.

The reader owns the connection: the export path already holds a
``read_only=True`` DuckDB handle, and this adds no second connection, so
the single-writer invariant is untouched.
"""

from __future__ import annotations

import json as _json
from typing import Any

import duckdb

# The canonical §9.0 predicate covers restricted_pending_opt_in and
# personal_reading. Calling it rather than importing its private backing set or
# re-listing classes keeps this export surface on the supported policy seam.
from substrate.graph.retrieval_gate import is_chunk_body_withheld

_RESOLUTION_BATCH_SIZE = 500


def _paragraph_sort_key(key: str) -> tuple[int, Any]:
    """Order ``prose_provenance`` paragraph keys numerically.

    The keys are paragraph indices stored as strings ("0", "1", ...,
    "10"); a plain lexical sort would place "10" before "2". Numeric keys
    sort in group 0 by int value; any non-numeric key degrades to group 1
    ordered lexically, so a malformed map never raises. The leading group
    int keeps the two groups from ever comparing an int against a str."""
    try:
        return (0, int(key))
    except (TypeError, ValueError):
        return (1, key)


def _resolve_blocks_to_documents(
    con: duckdb.DuckDBPyConnection,
    block_ids: list[str],
) -> dict[str, str]:
    """Resolve many block IDs without an export-time N+1 query cascade.

    Mirrors the canonical two-tier resolver in
    ``substrate.graph.insight_question``: node metadata first, then a
    ``supported_by`` edge. Other relations are never followed because they do
    not establish grounding and can cross rights boundaries. The edge query is
    deterministically ordered so ``setdefault`` chooses the lexicographically
    first grounding document when several exist. Unknown/user-authored block
    IDs simply contribute no source.
    """
    resolved: dict[str, str] = {}
    for start in range(0, len(block_ids), _RESOLUTION_BATCH_SIZE):
        batch = block_ids[start : start + _RESOLUTION_BATCH_SIZE]
        placeholders = ",".join("?" for _ in batch)
        node_rows = con.execute(
            f"SELECT node_id, metadata FROM nodes WHERE node_id IN ({placeholders})",
            batch,
        ).fetchall()
        for node_id, metadata_raw in node_rows:
            if not metadata_raw:
                continue
            try:
                metadata = _json.loads(metadata_raw)
            except (TypeError, ValueError):
                continue
            if isinstance(metadata, dict) and metadata.get("source_document_id"):
                resolved[str(node_id)] = str(metadata["source_document_id"])

        edge_rows = con.execute(
            "SELECT source_node_id, source_document_id FROM edges "
            f"WHERE source_node_id IN ({placeholders}) "
            "AND relation = 'supported_by' AND source_document_id IS NOT NULL "
            "ORDER BY source_node_id, source_document_id",
            batch,
        ).fetchall()
        for node_id, document_id in edge_rows:
            resolved.setdefault(str(node_id), str(document_id))
    return resolved


def resolve_deliverable_sources(
    con: duckdb.DuckDBPyConnection, deliverable_id: str
) -> list[str]:
    """Ordered, de-duplicated list of §9.0-gated source-document titles
    grounding a deliverable's prose.

    Order is by first appearance — ``section_index``, then
    ``paragraph_index``, then block order within a paragraph — and each
    document is named **once** even if cited across many paragraphs or
    sections. The list is safe to render into a public / monetized export:

    * a document whose ``content_class`` the canonical non-privileged policy
      withholds (including ``personal_reading`` and
      ``restricted_pending_opt_in``) is dropped — never named, never counted,
      indistinguishable from having no source;
    * a document with an empty / NULL title is dropped — we never
      fabricate a title, and an "Untitled" bullet would be noise (and
      could imply a source exists without naming it).

    Returns ``[]`` when the deliverable has no provenance, no resolvable
    grounding documents, or none that survive the §9.0 gate. The caller
    renders a Sources section only when this is non-empty, so a
    fully-withheld deliverable looks exactly like a source-less one."""
    sec_rows = con.execute(
        "SELECT prose_provenance FROM deliverable_sections "
        "WHERE deliverable_id = ? ORDER BY section_index ASC",
        [deliverable_id],
    ).fetchall()

    # Pass 1: collect block ids in first-appearance order, de-duplicated.
    ordered_block_ids: list[str] = []
    seen_blocks: set[str] = set()
    for (prov_raw,) in sec_rows:
        if not prov_raw:
            continue
        try:
            prov = _json.loads(prov_raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(prov, dict):
            continue
        for key in sorted(prov, key=_paragraph_sort_key):
            blocks = prov.get(key)
            if not isinstance(blocks, list):
                continue
            for b in blocks:
                if not isinstance(b, str) or b in seen_blocks:
                    continue
                seen_blocks.add(b)
                ordered_block_ids.append(b)

    if not ordered_block_ids:
        return []

    # Pass 2: resolve blocks -> documents (first-appearance, de-duplicated).
    block_to_doc = _resolve_blocks_to_documents(con, ordered_block_ids)
    ordered_doc_ids: list[str] = []
    seen_docs: set[str] = set()
    for b in ordered_block_ids:
        doc = block_to_doc.get(b)
        if doc and doc not in seen_docs:
            seen_docs.add(doc)
            ordered_doc_ids.append(doc)

    if not ordered_doc_ids:
        return []

    # Pass 3: fetch titles + content_class, then apply the §9.0 gate.
    placeholders = ",".join("?" for _ in ordered_doc_ids)
    doc_rows = con.execute(
        f"SELECT document_id, title, content_class FROM documents "
        f"WHERE document_id IN ({placeholders})",
        list(ordered_doc_ids),
    ).fetchall()
    doc_title: dict[str, Any] = {r[0]: r[1] for r in doc_rows}
    doc_cc: dict[str, Any] = {r[0]: r[2] for r in doc_rows}

    titles: list[str] = []
    for doc in ordered_doc_ids:
        withheld, _ = is_chunk_body_withheld(doc_cc.get(doc))
        if withheld:
            continue  # §9.0: personal_reading / restricted is never named
        title = (doc_title.get(doc) or "").strip()
        if not title:
            continue  # never fabricate a title
        titles.append(title)
    return titles
