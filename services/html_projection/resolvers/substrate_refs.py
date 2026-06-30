"""Resolve graph node ref_ids to rights-aware export payloads (HPRJ).

Reads the live DuckDB graph via ``connect_read`` only. Reports source-document
``content_class`` / ``ip_holder_id`` faithfully; the notebook/deliverable adapters
apply ``SERVABLE_CONTENT_CLASSES`` filtering — this module must not pre-filter.
"""

from __future__ import annotations

import json
from typing import Any

from runtime.db_lock import connect_read

from ..adapters.notebook import ResolvedRefData

_KIND_PAYLOAD_KEYS: dict[str, str] = {
    "claim": "statement",
    "question": "question",
    "insight": "statement",
}


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


def _source_document_id(con, node_id: str, metadata_raw: str | None) -> str | None:
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
    con, document_id: str
) -> tuple[str | None, str | None, str | None]:
    row = con.execute(
        "SELECT title, content_class, ip_holder_id FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    if row is None:
        return None, None, None
    title, content_class, ip_holder_id = row
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
            )
    finally:
        con.close()

    return out