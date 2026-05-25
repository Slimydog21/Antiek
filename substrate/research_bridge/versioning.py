"""DRW SPR-08 M6 — versioned raw_text for editable ingested material.

The reading surface (SPR-10) lets a user edit an ingested document. An edit
must NOT destroy the original provenance — so editing creates a *new*
document row (content-addressed by the new text) that links back to the
original via ``metadata.parent_document_id`` + an incremented ``version``.
The original row is left byte-for-byte intact, so its provenance
(ip_holder_id, source, original raw_text) is provably preserved and the
version chain is walkable.

No schema change: the documents table already has ``raw_text`` + ``metadata``;
the version lineage rides in metadata, which keeps SPR-08 additive.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, List, Optional

try:
    from ...runtime.db_lock import LockedConnection, connect_read, connect_write
    from ..graph.ops import content_addressed_id, insert_document
    from ..graph.insight_question import graph_db_path
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection, connect_read, connect_write  # type: ignore[no-redef]
    from substrate.graph.ops import content_addressed_id, insert_document  # type: ignore[no-redef]
    from substrate.graph.insight_question import graph_db_path  # type: ignore[no-redef]


@dataclass(frozen=True)
class DocumentVersion:
    document_id: str
    version: int
    parent_document_id: Optional[str]


def _doc(con, document_id: str):
    return con.execute(
        "SELECT document_type, source_tier, source_uri, title, raw_text, "
        "investigation_id, ip_holder_id, content_class, metadata "
        "FROM documents WHERE document_id = ?", [document_id],
    ).fetchone()


def _meta(raw) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def create_document_version(
    con: LockedConnection,
    *,
    original_document_id: str,
    new_text: str,
    edited_by: str = "__operator__",
) -> str:
    """Persist an edit as a new version. Returns the new document_id. The
    original row is untouched (provenance preserved). Editing to identical
    text is a no-op that returns the original id."""
    row = _doc(con, original_document_id)
    if row is None:
        raise ValueError(f"no document {original_document_id!r} to version")
    (document_type, source_tier, source_uri, title, raw_text,
     investigation_id, ip_holder_id, content_class, metadata_json) = row
    if new_text == raw_text:
        return original_document_id  # nothing changed

    meta = _meta(metadata_json)
    rb = dict(meta.get("research_bridge", {}))
    parent = original_document_id
    root = rb.get("version_root", original_document_id)
    new_version = int(rb.get("version", 1)) + 1
    rb.update({"version": new_version, "parent_document_id": parent,
               "version_root": root, "edited_by": edited_by,
               "raw_sha256": hashlib.sha256(new_text.encode()).hexdigest()})
    meta["research_bridge"] = rb

    new_id = content_addressed_id("doc", f"version|{root}|{new_version}|{rb['raw_sha256']}")
    insert_document(
        con, document_id=new_id, source_tier=int(source_tier),
        document_type=document_type, source_uri=source_uri,
        title=(title or "") + f" (v{new_version})", raw_text=new_text,
        investigation_id=investigation_id, ip_holder_id=ip_holder_id,
        content_class=content_class, metadata=meta, on_conflict="ignore",
    )
    return new_id


def document_versions(con, root_or_any_id: str) -> List[DocumentVersion]:
    """Walk the version chain for a document family, ordered by version.
    Accepts the root id or any version id (resolves to the root)."""
    row = _doc(con, root_or_any_id)
    if row is None:
        return []
    rb = _meta(row[8]).get("research_bridge", {})
    root = rb.get("version_root", root_or_any_id)
    # All documents whose version_root is `root`, plus the root itself.
    rows = con.execute(
        "SELECT document_id, metadata FROM documents "
        "WHERE document_id = ? OR metadata LIKE ?",
        [root, f'%"version_root": "{root}"%'],
    ).fetchall()
    versions = []
    for did, m in rows:
        rbm = _meta(m).get("research_bridge", {})
        versions.append(DocumentVersion(
            document_id=did, version=int(rbm.get("version", 1)),
            parent_document_id=rbm.get("parent_document_id"),
        ))
    return sorted(versions, key=lambda v: v.version)
