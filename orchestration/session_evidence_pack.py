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

from runtime.db_lock import connect_read
from substrate.schemas import ActionType

# v2: ``PackChunk.text`` is the cited chunk's substrate text. A v1 pack's
# ``text`` is the generated note itself, so reading one as source text would
# certify the note; v1 is not accepted.
SCHEMA_VERSION = 2
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
    """One evidence chunk with a complete provenance chain.

    ``text`` is the chunk's own source text, and it is the only text a chunk
    carries. The gather note that cited the chunk is a generated claim about
    it, and nothing on this path can establish that the chunk entails it: a
    word-overlap check passes a reversed relationship ("Beta acquired Alpha")
    or swapped figures built from the source's own words. So the note is not
    part of the pack, and ``extra="forbid"`` refuses a chunk that carries one."""

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


def _substrate_chunk(
    con: Any,
    chunk_id: str,
) -> tuple[str, str | None, str | None, str] | None:
    """``(document_id, ip_holder_id, title, text)`` for a chunk the substrate
    holds.

    ``None`` when the chunk row, or the document it cites, does not exist.
    The pack reads both ids, the ip_holder and the chunk text from these rows,
    never from producer-written node metadata, so it cannot cite a chunk or
    document that exists nowhere, nor put words in a real chunk's mouth."""
    row = con.execute(
        "SELECT c.document_id, d.ip_holder_id, d.title, c.text FROM chunks c "
        "JOIN documents d ON d.document_id = c.document_id "
        "WHERE c.chunk_id = ?",
        [chunk_id],
    ).fetchone()
    if row is None or row[3] is None or not str(row[3]).strip():
        return None
    return str(row[0]), row[1], row[2], str(row[3])


def _load_problem_question(
    session_id: str,
    *,
    events_dir: str,
    db_path: str,
    plan_root_node_id: str | None,
) -> str:
    from substrate.event_log import trajectory

    if plan_root_node_id:

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
    seen: set[tuple[str, str]] = set()


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

                if not str(label).strip():
                    continue
                # Evidence is admitted only when its chunk and that chunk's
                # document exist in the substrate. A node with no chunk (the
                # contract stub's placeholder note, an Exa "no servable
                # source" note) is not evidence, so it stays out of the pack
                # rather than riding a minted ``chunk-<node>`` /
                # ``doc-gather-*`` pair into the synthesizer as "direct"
                # support. A node whose claimed document is not the chunk's
                # document has a broken chain and is dropped too.
                if not meta_chunk:
                    continue
                resolved = _substrate_chunk(con, str(meta_chunk))
                if resolved is None:
                    continue
                document_id, ip_holder, doc_title, chunk_text = resolved
                if meta_doc and str(meta_doc) != document_id:
                    continue
                chunk_id = str(meta_chunk)
                # The chunk's own text is the evidence. The node label (the
                # generated note) is not carried: nothing here can show the
                # chunk entails it. With the note gone, several notes of one leaf
                # citing the same chunk would repeat one excerpt as separate
                # supporting claims, so each (leaf, chunk) enters once.
                if (iid, chunk_id) in seen:
                    continue
                seen.add((iid, chunk_id))

                if document_id not in documents:
                    documents[document_id] = PackDocument(
                        document_id=document_id,
                        title=str(doc_title) if doc_title else document_id,
                        ip_holder_id=ip_holder,
                        source_tier=3,
                    )

                doc = documents[document_id]
                chunks.append(
                    PackChunk(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        ip_holder_id=doc.ip_holder_id,
                        text=chunk_text,
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