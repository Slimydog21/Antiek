"""Operator-reviewed twin notes -> canonical Write outline.

This is deliberately a narrow orchestration seam.  Twin text is resolved from
the server-side engagement store, then the sanctioned insight/question graph
promoters and the existing Write composition primitives share one locked
DuckDB transaction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from runtime.db_lock import connect_write
from substrate.event_log import emit_typed
from substrate.floating_session.store import SessionStore
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.insight_question import (
    insight_node_id,
    promote_insight,
    promote_question,
    question_node_id,
)
from substrate.graph.ops import insert_deliverable, insert_section
from substrate.schemas.events import GraphNodeInsertedPayload, OutlineBlockPlacedPayload
from substrate.write.outline_block import place_node_block

from .store import EngagementStore
from .twin import TwinNote, list_twin_notes

ProvenancePrecision = Literal["chunk", "document"]
TwinBlockKind = Literal["insight", "open_question"]
TwinNodeType = Literal["insight", "question"]


@dataclass(frozen=True)
class WriteHandoffResult:
    deliverable_id: str
    promoted_note_ids: tuple[str, ...]
    skipped_note_ids: tuple[str, ...]
    provenance_precision: ProvenancePrecision
    replayed: bool


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha256(key.encode()).hexdigest()[:20]}"


def _submission_key(
    *, asset_id: str, session_id: str, spawn_id: str,
    investigation_id: str, title: str, note_ids: list[str],
) -> str:
    return json.dumps(
        ["twins-to-write:v1", asset_id, session_id, spawn_id,
         investigation_id, title, note_ids],
        ensure_ascii=False, separators=(",", ":"),
    )


def _validated_notes(
    *, store: EngagementStore, asset_id: str, spawn_id: str,
    investigation_id: str, note_ids: list[str],
) -> list[TwinNote]:
    by_id = {n.note_id: n for n in list_twin_notes(asset_id, store=store)}
    notes: list[TwinNote] = []
    seen: set[str] = set()
    for note_id in note_ids:
        if note_id in seen:
            raise ValueError(f"duplicate twin note id: {note_id}")
        seen.add(note_id)
        note = by_id.get(note_id)
        if note is None:
            raise ValueError(f"twin note does not belong to this asset: {note_id}")
        if note.source_spawn_id != spawn_id:
            raise ValueError(f"twin note does not belong to this spawn: {note_id}")
        if note.investigation_id != investigation_id:
            raise ValueError(f"twin note does not belong to this investigation: {note_id}")
        notes.append(note)
    return notes


def send_selected_twins_to_write(
    *, engagement_store: EngagementStore, session_store: SessionStore,
    asset_id: str, session_id: str, spawn_id: str, investigation_id: str,
    title: str, note_ids: list[str], db_path: str | None = None,
) -> WriteHandoffResult:
    """Promote selected twins and create their ordered Write outline atomically."""
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("title is required")
    if not note_ids:
        raise ValueError("select at least one twin note")

    session = session_store.get_session(session_id)
    spawn = engagement_store.get_spawn(spawn_id)
    expected = {
        "parent_asset_id": asset_id,
        "spawn_id": spawn_id,
        "investigation_id": investigation_id,
    }
    if session is None or any(session.get(k) != v for k, v in expected.items()):
        raise ValueError("session does not match the stated asset/spawn lineage")
    if spawn is None or spawn.get("parent_asset_id") != asset_id or (
        spawn.get("investigation_id") != investigation_id
    ):
        raise ValueError("spawn does not match the stated asset/investigation lineage")

    notes = _validated_notes(
        store=engagement_store, asset_id=asset_id, spawn_id=spawn_id,
        investigation_id=investigation_id, note_ids=note_ids,
    )
    key = _submission_key(
        asset_id=asset_id, session_id=session_id, spawn_id=spawn_id,
        investigation_id=investigation_id, title=clean_title, note_ids=note_ids,
    )
    deliverable_id = _stable_id("dlv", key)
    section_id = _stable_id("sec", key)
    path = ensure_initialized(db_path or default_db_path())
    con = connect_write(path, purpose="engagement/send_twins_to_write")
    committed_nodes: list[tuple[str, TwinNote]] = []
    committed_blocks: list[tuple[str, TwinBlockKind, int]] = []
    try:
        con.execute("BEGIN")
        try:
            document = con.execute(
                "SELECT document_id FROM documents WHERE document_id = ?",
                [asset_id],
            ).fetchone()
            if document is None:
                raise ValueError("parent asset does not resolve to a canonical document")

            region_id = session.get("region_id")
            chunk = None
            if region_id:
                chunk = con.execute(
                    "SELECT chunk_id FROM chunks WHERE chunk_id = ? AND document_id = ?",
                    [region_id, asset_id],
                ).fetchone()
            chunk_id = chunk[0] if chunk else None
            precision: ProvenancePrecision = "chunk" if chunk_id else "document"

            prior = con.execute(
                "SELECT metadata FROM deliverables WHERE deliverable_id = ?",
                [deliverable_id],
            ).fetchone()
            if prior is not None:
                metadata = json.loads(prior[0] or "{}")
                if metadata.get("twin_handoff_key") != key:
                    raise RuntimeError("deterministic handoff id collision")
                original_precision = metadata.get("provenance_precision")
                if original_precision not in ("chunk", "document"):
                    raise RuntimeError("handoff replay has invalid provenance metadata")
                con.execute("COMMIT")
                return WriteHandoffResult(
                    deliverable_id, (), tuple(note_ids), original_precision, True,
                )

            common_meta = {
                "asset_id": asset_id, "spawn_id": spawn_id,
                "investigation_id": investigation_id,
                "provenance_precision": precision,
            }
            node_ids: list[str] = []
            for note in notes:
                metadata = {**common_meta, "twin_note_id": note.note_id}
                expected_node_id = (
                    insight_node_id(note.text)
                    if note.kind == "insight"
                    else question_node_id(note.text)
                )
                existing = con.execute(
                    "SELECT node_type, metadata FROM nodes WHERE node_id = ?",
                    [expected_node_id],
                ).fetchone()
                if existing is not None:
                    existing_meta = json.loads(existing[1] or "{}")
                    expected_type = "insight" if note.kind == "insight" else "question"
                    required = {
                        "asset_id": asset_id,
                        "spawn_id": spawn_id,
                        "investigation_id": investigation_id,
                        "twin_note_id": note.note_id,
                        "provenance_precision": precision,
                        "source_document_id": asset_id,
                    }
                    if existing[0] != expected_type or any(
                        existing_meta.get(field) != value
                        for field, value in required.items()
                    ) or existing_meta.get("chunk_id") != chunk_id:
                        raise ValueError(
                            "selected note text already exists with different provenance"
                        )
                if note.kind == "insight":
                    node_id = promote_insight(
                        text=note.text, investigation_id=investigation_id,
                        source_document_id=asset_id, chunk_id=chunk_id,
                        metadata=metadata, con=con, emit_event=False,
                    )
                else:
                    node_id = promote_question(
                        text=note.text, investigation_id=investigation_id,
                        anchor_region_id=chunk_id, source_document_id=asset_id,
                        chunk_id=chunk_id, metadata=metadata, con=con,
                        emit_event=False,
                    )
                node_ids.append(node_id)
                if existing is None:
                    committed_nodes.append((node_id, note))

            insert_deliverable(
                con, title=clean_title, deliverable_kind="general_essay",
                investigation_root_id=investigation_id,
                metadata={**common_meta, "twin_handoff_key": key,
                          "twin_note_ids": note_ids},
                deliverable_id=deliverable_id,
            )
            insert_section(
                con, deliverable_id=deliverable_id, section_index=0,
                title="Selected twin notes", section_id=section_id,
            )
            for index, (note, node_id) in enumerate(zip(notes, node_ids, strict=True)):
                block_id = _stable_id("oblk", f"{key}:{index}:{note.note_id}")
                block_kind: TwinBlockKind = (
                    "insight" if note.kind == "insight" else "open_question"
                )
                place_node_block(
                    con, section_id=section_id, node_id=node_id,
                    block_kind=block_kind,
                    block_index=index, deliverable_id=deliverable_id,
                    investigation_id=investigation_id,
                    outline_block_id=block_id,
                    metadata={**common_meta, "twin_note_id": note.note_id},
                    emit_event=False,
                )
                committed_blocks.append((block_id, block_kind, index))
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()
    for node_id, note in committed_nodes:
        node_type: TwinNodeType = (
            "insight" if note.kind == "insight" else "question"
        )
        emit_typed(
            investigation_id,
            GraphNodeInsertedPayload(
                node_id=node_id,
                canonical_label=note.text,
                node_type=node_type,
                graph_scope="depth",
                has_embedding=True,
            ),
            role="connector",
        )
    for block_id, block_kind, index in committed_blocks:
        emit_typed(
            investigation_id,
            OutlineBlockPlacedPayload(
                outline_block_id=block_id,
                deliverable_id=deliverable_id,
                section_id=section_id,
                block_kind=block_kind,
                provenance_kind="graph_node",
                node_id=node_ids[index],
                block_index=index,
            ),
            role="write_composition",
        )
    return WriteHandoffResult(
        deliverable_id, tuple(note_ids), (), precision, False,
    )


__all__ = ["WriteHandoffResult", "send_selected_twins_to_write"]
