"""SessionEvidencePack — typed DRW gather → Loop 1 Phase 6+ bridge (SPR-DRL-05).

The pack is the stable handoff artifact between cascade merge and Loop 1
synthesis tail. Exa / parallel web adapters fill ``chunks`` later; the schema
shape stays constant.

Rejected alternative: pipe raw ``StepEvent`` JSONL into the synthesizer —
the constraint loop expects typed evidence + parameter artifacts, not a
multiplexed step stream.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from substrate.schemas import ActionType

SCHEMA_VERSION = 1
_SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})


class PackDocument(BaseModel):
    """One document referenced by pack chunks — carries ``ip_holder_id`` even
    when null (substrate provenance invariant)."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    ip_holder_id: str | None = None
    source_tier: int = Field(default=3, ge=1, le=5)


class PackChunk(BaseModel):
    """One evidence chunk with a complete provenance chain."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    ip_holder_id: str | None = None
    text: str
    source_investigation_id: str
    sub_question: str


class SessionEvidencePack(BaseModel):
    """Immutable merge artifact keyed by ``session_id``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    session_id: str
    problem_question: str
    chunks: list[PackChunk] = Field(default_factory=list)
    documents: list[PackDocument] = Field(default_factory=list)
    leaf_investigation_ids: list[str] = Field(default_factory=list)
    content_hash: str = ""

    @model_validator(mode="after")
    def _validate_provenance_and_hash(self) -> SessionEvidencePack:
        if self.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"unsupported schema_version {self.schema_version!r}; "
                f"supported={sorted(_SUPPORTED_SCHEMA_VERSIONS)}"
            )
        doc_by_id = {d.document_id: d for d in self.documents}
        if len(doc_by_id) != len(self.documents):
            raise ValueError("duplicate document_id in documents")
        for chunk in self.chunks:
            doc = doc_by_id.get(chunk.document_id)
            if doc is None:
                raise ValueError(
                    f"chunk {chunk.chunk_id!r} references unknown "
                    f"document {chunk.document_id!r}"
                )
            chunk_ip = chunk.ip_holder_id
            doc_ip = doc.ip_holder_id
            if chunk_ip != doc_ip:
                raise ValueError(
                    f"chunk {chunk.chunk_id!r} ip_holder_id {chunk_ip!r} "
                    f"!= document {chunk.document_id!r} ip_holder_id {doc_ip!r}"
                )
        expected = compute_content_hash(
            session_id=self.session_id,
            problem_question=self.problem_question,
            chunks=self.chunks,
            documents=self.documents,
            leaf_investigation_ids=self.leaf_investigation_ids,
            schema_version=self.schema_version,
        )
        if self.content_hash and self.content_hash != expected:
            raise ValueError(
                f"content_hash mismatch: got {self.content_hash!r}, "
                f"expected {expected!r}"
            )
        if not self.content_hash:
            object.__setattr__(self, "content_hash", expected)
        return self


class SessionEvidencePackError(ValueError):
    """Raised when a pack cannot be built or validated."""


def compute_content_hash(
    *,
    session_id: str,
    problem_question: str,
    chunks: Sequence[PackChunk],
    documents: Sequence[PackDocument],
    leaf_investigation_ids: Sequence[str],
    schema_version: int = SCHEMA_VERSION,
) -> str:
    """Deterministic SHA-256 over canonical pack body (excludes content_hash)."""
    body = {
        "schema_version": schema_version,
        "session_id": session_id,
        "problem_question": problem_question,
        "chunks": [c.model_dump() for c in sorted(chunks, key=lambda c: c.chunk_id)],
        "documents": [
            d.model_dump() for d in sorted(documents, key=lambda d: d.document_id)
        ],
        "leaf_investigation_ids": sorted(leaf_investigation_ids),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def parse_session_evidence_pack(data: dict[str, Any]) -> SessionEvidencePack:
    """Parse + validate a pack dict. Raises ``SessionEvidencePackError``."""
    try:
        return SessionEvidencePack.model_validate(data)
    except ValidationError as exc:
        raise SessionEvidencePackError(str(exc)) from exc


def _document_ip_holder(
    con: Any,
    document_id: str,
) -> str | None:
    row = con.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    if row is None:
        return None
    return row[0]


def _load_problem_question(
    session_id: str,
    *,
    events_dir: str,
    db_path: str,
    plan_root_node_id: str | None,
) -> str:
    from substrate.event_log import trajectory

    if plan_root_node_id:
        from runtime.db_lock import connect_read

        con = connect_read(db_path)
        try:
            row = con.execute(
                "SELECT canonical_label FROM nodes WHERE node_id = ?",
                [plan_root_node_id],
            ).fetchone()
            if row and row[0]:
                return str(row[0])
        finally:
            con.close()

    for ev in trajectory(session_id, events_dir=events_dir):
        if ev.get("action_type") == "cascade.launched":
            payload = ev.get("payload") or {}
            if isinstance(payload, dict):
                root = payload.get("plan_root_node_id")
                if root:
                    return _load_problem_question(
                        session_id,
                        events_dir=events_dir,
                        db_path=db_path,
                        plan_root_node_id=str(root),
                    )
    return session_id


def build_session_evidence_pack(
    session_id: str,
    *,
    events_dir: str,
    db_path: str,
    researches: Sequence[tuple[str, str]],
    plan_root_node_id: str | None = None,
) -> SessionEvidencePack:
    """Build a pack from cascade merge state + per-leaf JSONL trajectories.

    ``researches`` is ``(investigation_id, sub_question)`` pairs for session
    members (from ``reconstruct_session`` or live ``CascadeSession.status``).
    """
    from substrate.event_log import trajectory

    problem_question = _load_problem_question(
        session_id,
        events_dir=events_dir,
        db_path=db_path,
        plan_root_node_id=plan_root_node_id,
    )

    documents: dict[str, PackDocument] = {}
    chunks: list[PackChunk] = []
    leaf_ids: list[str] = []

    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        for iid, sub_q in researches:
            leaf_ids.append(iid)
            rows = trajectory(iid, events_dir=events_dir)
            for ev in rows:
                if ev.get("action_type") != ActionType.GRAPH_NODE_INSERTED.value:
                    continue
                payload = ev.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                if payload.get("node_type") != "insight":
                    continue
                node_id = payload.get("node_id")
                label = payload.get("canonical_label") or ""
                if not node_id:
                    continue

                meta_chunk = None
                meta_doc = None
                meta_ip = None
                node_row = con.execute(
                    "SELECT canonical_label, metadata FROM nodes WHERE node_id = ?",
                    [node_id],
                ).fetchone()
                if node_row:
                    if node_row[0]:
                        label = str(node_row[0])
                    node_meta = node_row[1]
                    if isinstance(node_meta, str):
                        try:
                            node_meta = json.loads(node_meta)
                        except json.JSONDecodeError:
                            node_meta = None
                    if isinstance(node_meta, dict):
                        meta_chunk = node_meta.get("chunk_id")
                        meta_doc = node_meta.get("source_document_id")
                        meta_ip = node_meta.get("ip_holder_id")

                if not str(label).strip():
                    continue

                document_id = (
                    str(meta_doc)
                    if meta_doc
                    else f"doc-gather-{session_id}-{iid}"
                )
                chunk_id = (
                    str(meta_chunk) if meta_chunk else f"chunk-{node_id}"
                )

                if document_id not in documents:
                    ip_holder = (
                        str(meta_ip) if meta_ip is not None
                        else _document_ip_holder(con, document_id)
                    )
                    title = (
                        f"Gather source ({iid})"
                        if document_id.startswith("doc-gather-")
                        else document_id
                    )
                    if not document_id.startswith("doc-gather-"):
                        row = con.execute(
                            "SELECT title FROM documents WHERE document_id = ?",
                            [document_id],
                        ).fetchone()
                        if row and row[0]:
                            title = str(row[0])
                    documents[document_id] = PackDocument(
                        document_id=document_id,
                        title=title,
                        ip_holder_id=ip_holder,
                        source_tier=3,
                    )

                doc = documents[document_id]
                chunks.append(
                    PackChunk(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        ip_holder_id=doc.ip_holder_id,
                        text=str(label).strip(),
                        source_investigation_id=iid,
                        sub_question=sub_q,
                    )
                )
    finally:
        con.close()

    content_hash = compute_content_hash(
        session_id=session_id,
        problem_question=problem_question,
        chunks=chunks,
        documents=list(documents.values()),
        leaf_investigation_ids=leaf_ids,
    )
    return SessionEvidencePack(
        session_id=session_id,
        problem_question=problem_question,
        chunks=chunks,
        documents=list(documents.values()),
        leaf_investigation_ids=sorted(leaf_ids),
        content_hash=content_hash,
    )