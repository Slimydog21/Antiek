"""Commit a reviewed engagement draft into the canonical deliverable graph."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.graph.ops import content_addressed_id, insert_deliverable, insert_section

from .store import EngagementStore


class CanonicalMergeConflict(ValueError):
    """The reviewed draft or canonical target no longer matches authority."""


@dataclass(frozen=True)
class CanonicalMergeCommit:
    deliverable_id: str
    draft_document_id: str
    old_revision: str | None
    new_revision: str
    section_id: str
    node_ids: tuple[str, ...]
    paragraph_count: int
    draft_sha256: str


def _json(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError) as exc:
        raise CanonicalMergeConflict("canonical metadata is invalid") from exc
    if not isinstance(decoded, dict):
        raise CanonicalMergeConflict("canonical metadata must be an object")
    return decoded


def _draft_hash(doc_model: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            doc_model,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _require_provenance(provenance: object, *, parent_asset_id: str) -> dict[str, Any]:
    if not isinstance(provenance, dict):
        raise CanonicalMergeConflict("every committed paragraph requires provenance")
    value = dict(provenance)
    kind = str(value.get("kind") or "")
    if value.get("parent_asset_id") != parent_asset_id or kind not in {
        "source",
        "empty",
        "selection",
        "research_output",
        "insight",
        "question",
        "twin_insight",
        "twin_question",
    }:
        raise CanonicalMergeConflict("paragraph provenance has no stable source authority")
    if kind in {"selection", "research_output", "insight", "question"} and not all(
        str(value.get(key) or "").strip() for key in ("spawn_id", "investigation_id")
    ):
        raise CanonicalMergeConflict("spawn paragraph provenance is incomplete")
    if kind.startswith("twin_"):
        twin_ids = value.get("twin_note_ids")
        if (
            not isinstance(twin_ids, list)
            or not twin_ids
            or not all(isinstance(note_id, str) and note_id.strip() for note_id in twin_ids)
        ):
            raise CanonicalMergeConflict("twin paragraph provenance is incomplete")
    references = value.get("source_reference_ids", [])
    if not isinstance(references, list) or not all(
        isinstance(reference_id, str) and reference_id.strip() for reference_id in references
    ):
        raise CanonicalMergeConflict("paragraph reference provenance is invalid")
    return value


def _insert_verified_node(
    con: LockedConnection,
    *,
    node_id: str,
    label: str,
    node_type: str,
    metadata: dict[str, Any],
) -> None:
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    existing = con.execute(
        "SELECT canonical_label, node_type, graph_scope, metadata FROM nodes WHERE node_id = ?",
        [node_id],
    ).fetchone()
    expected = (label, node_type, "depth", encoded)
    if existing is not None:
        if tuple(existing) != expected:
            raise CanonicalMergeConflict("canonical node identity collides with other state")
        return
    con.execute(
        "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
        "VALUES (?, ?, ?, 'depth', ?)",
        [node_id, label, node_type, encoded],
    )


def _target_revision(con: LockedConnection, deliverable_id: str) -> str:
    deliverable = con.execute(
        "SELECT title, deliverable_kind, investigation_root_id, owner_user_id, "
        "status, metadata "
        "FROM deliverables WHERE deliverable_id = ?",
        [deliverable_id],
    ).fetchone()
    if deliverable is None:
        raise KeyError(deliverable_id)
    deliverable_values = list(deliverable)
    metadata = _json(deliverable_values[-1])
    for key in (
        "revision",
        "previous_revision",
        "last_draft_sha256",
        "last_merge_section_id",
        "last_merge_node_ids",
        "last_draft_document_id",
    ):
        metadata.pop(key, None)
    deliverable_values[-1] = metadata
    sections = con.execute(
        "SELECT section_id, parent_section_id, section_index, title, prose_text, "
        "prose_provenance "
        "FROM deliverable_sections WHERE deliverable_id = ? "
        "ORDER BY section_index, section_id",
        [deliverable_id],
    ).fetchall()
    blocks = con.execute(
        "SELECT sb.section_id, sb.block_kind, sb.block_id, sb.block_index "
        "FROM section_blocks sb JOIN deliverable_sections s "
        "ON s.section_id = sb.section_id WHERE s.deliverable_id = ? "
        "ORDER BY sb.section_id, sb.block_index, sb.block_kind, sb.block_id",
        [deliverable_id],
    ).fetchall()
    outline_blocks = con.execute(
        "SELECT outline_block_id, section_id, block_kind, provenance_kind, node_id, "
        "source_block_kind, source_block_id, content, block_index, cluster_id, metadata "
        "FROM outline_blocks WHERE section_id IN "
        "(SELECT section_id FROM deliverable_sections WHERE deliverable_id = ?) "
        "ORDER BY section_id, block_index, outline_block_id",
        [deliverable_id],
    ).fetchall()
    node_ids = [str(row[2]) for row in blocks]
    for section in sections:
        provenance = _json(section[5]) if section[5] is not None else {}
        for values in provenance.values():
            if isinstance(values, list):
                node_ids.extend(str(value) for value in values)
    node_ids = list(dict.fromkeys(node_ids))
    nodes = (
        con.execute(
            "SELECT node_id, canonical_label, node_type, graph_scope, metadata "
            "FROM nodes WHERE node_id = ANY(?) ORDER BY node_id",
            [node_ids],
        ).fetchall()
        if node_ids
        else []
    )
    edges = (
        con.execute(
            "SELECT edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, source_tier, extraction_confidence, graph_scope, "
            "investigation_id, metadata FROM edges "
            "WHERE source_node_id = ANY(?) OR target_node_id = ANY(?) ORDER BY edge_id",
            [node_ids, node_ids],
        ).fetchall()
        if node_ids
        else []
    )
    material = json.dumps(
        {
            "deliverable": deliverable_values,
            "sections": [list(row) for row in sections],
            "blocks": [list(row) for row in blocks],
            "outline_blocks": [list(row) for row in outline_blocks],
            "nodes": [list(row) for row in nodes],
            "edges": [list(row) for row in edges],
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def canonical_deliverable_revision(con: LockedConnection, deliverable_id: str) -> str:
    return _target_revision(con, deliverable_id)


def load_reviewed_document_model(
    con: LockedConnection, deliverable_id: str, section_id: str
) -> dict[str, Any]:
    row = con.execute(
        "SELECT metadata FROM deliverables WHERE deliverable_id = ?", [deliverable_id]
    ).fetchone()
    if row is None:
        raise KeyError(deliverable_id)
    metadata = _json(row[0])
    if metadata.get("last_merge_section_id") != section_id:
        raise CanonicalMergeConflict("canonical section is not the committed review")
    model = metadata.get("reviewed_doc_model")
    if not isinstance(model, dict) or _draft_hash(model) != metadata.get("last_draft_sha256"):
        raise CanonicalMergeConflict("canonical reviewed document model is invalid")
    return model


def load_latest_reviewed_document_model(
    con: LockedConnection, deliverable_id: str
) -> tuple[dict[str, Any], str, str, str]:
    row = con.execute(
        "SELECT metadata FROM deliverables WHERE deliverable_id = ?", [deliverable_id]
    ).fetchone()
    if row is None:
        raise KeyError(deliverable_id)
    metadata = _json(row[0])
    section_id = str(metadata.get("last_merge_section_id") or "")
    revision = str(metadata.get("revision") or "")
    draft_sha = str(metadata.get("last_draft_sha256") or "")
    if not section_id or not revision or not draft_sha:
        raise CanonicalMergeConflict("deliverable is not canonical reviewed research")
    if _target_revision(con, deliverable_id) != revision:
        raise CanonicalMergeConflict("canonical reviewed research has drifted")
    model = load_reviewed_document_model(con, deliverable_id, section_id)
    return model, section_id, revision, draft_sha


def commit_reviewed_draft(
    *,
    con: LockedConnection,
    engagement_store: EngagementStore,
    draft_document_id: str,
    target_deliverable_id: str,
    expected_revision: str | None,
    reviewed_draft_sha256: str,
    create_combined: bool,
    owner_user_id: str = "__operator__",
) -> CanonicalMergeCommit:
    draft = engagement_store.get_document(draft_document_id)
    if not isinstance(draft, dict) or draft.get("mode") != "draft_combined":
        raise CanonicalMergeConflict("reviewed draft_combined document is required")
    doc_model = draft.get("doc_model")
    if not isinstance(doc_model, dict):
        raise CanonicalMergeConflict("reviewed draft lacks a document model")
    draft_sha = _draft_hash(doc_model)
    if draft.get("draft_sha256") != draft_sha:
        raise CanonicalMergeConflict("reviewed draft hash conflicts with stored content")
    if reviewed_draft_sha256 != draft_sha:
        raise CanonicalMergeConflict("reviewed draft changed after operator review")

    existing = con.execute(
        "SELECT metadata FROM deliverables WHERE deliverable_id = ?",
        [target_deliverable_id],
    ).fetchone()
    old_revision: str | None = None
    if existing is None:
        if not create_combined or expected_revision not in {None, "new"}:
            raise KeyError(target_deliverable_id)
        draft_title = str(doc_model.get("title") or draft.get("title") or "Combined research")
        canonical_title = draft_title.removeprefix("[Draft] ").strip()
        insert_deliverable(
            con,
            deliverable_id=target_deliverable_id,
            title=canonical_title or "Combined research",
            deliverable_kind="research_memo",
            investigation_root_id=None,
            owner_user_id=owner_user_id,
            metadata={
                "source_document_id": draft.get("parent_asset_id"),
                "created_from_draft": draft_document_id,
            },
        )
    else:
        metadata = _json(existing[0])
        if (
            metadata.get("last_draft_sha256") == draft_sha
            and metadata.get("last_draft_document_id") == draft_document_id
        ):
            section_id = str(metadata.get("last_merge_section_id") or "")
            node_ids = tuple(str(value) for value in metadata.get("last_merge_node_ids") or ())
            section = con.execute(
                "SELECT deliverable_id FROM deliverable_sections WHERE section_id = ?",
                [section_id],
            ).fetchone()
            existing_nodes = (
                con.execute(
                    "SELECT count(*) FROM nodes WHERE node_id = ANY(?)", [list(node_ids)]
                ).fetchone()[0]
                if node_ids
                else 0
            )
            if (
                section != (target_deliverable_id,)
                or existing_nodes != len(node_ids)
                or _target_revision(con, target_deliverable_id) != metadata.get("revision")
            ):
                raise CanonicalMergeConflict(
                    "recorded canonical merge no longer matches target state"
                )
            return CanonicalMergeCommit(
                deliverable_id=target_deliverable_id,
                draft_document_id=draft_document_id,
                old_revision=metadata.get("previous_revision"),
                new_revision=str(metadata.get("revision")),
                section_id=section_id,
                node_ids=node_ids,
                paragraph_count=len(node_ids),
                draft_sha256=draft_sha,
            )
        old_revision = _target_revision(con, target_deliverable_id)
        if expected_revision != old_revision:
            raise CanonicalMergeConflict("canonical target revision is stale")

    parent_asset_id = str(draft.get("parent_asset_id") or "").strip()
    if not parent_asset_id:
        raise CanonicalMergeConflict("reviewed draft lacks parent source authority")
    paragraphs: list[tuple[str, dict[str, Any]]] = []
    for block in doc_model.get("content") or ():
        if not isinstance(block, dict) or block.get("type") != "paragraph":
            continue
        text = "".join(
            str(part.get("text") or "")
            for part in block.get("content") or ()
            if isinstance(part, dict)
        )
        provenance = (block.get("attrs") or {}).get("provenance")
        if not text.strip():
            raise CanonicalMergeConflict("every committed paragraph requires provenance")
        paragraphs.append((text, _require_provenance(provenance, parent_asset_id=parent_asset_id)))
    if not paragraphs:
        raise CanonicalMergeConflict("reviewed draft has no provenance-bearing paragraphs")

    node_ids: list[str] = []
    prose_provenance: dict[int, list[str]] = {}
    parent_node_id = content_addressed_id("node", f"source-asset|{parent_asset_id}")
    canonical_source_document = con.execute(
        "SELECT document_id FROM documents WHERE document_id = ?", [parent_asset_id]
    ).fetchone()
    _insert_verified_node(
        con,
        node_id=parent_node_id,
        label=parent_asset_id,
        node_type="entity",
        metadata={
            "origin": "canonical_source_asset",
            "source_document_id": parent_asset_id,
        },
    )
    for index, (text, provenance) in enumerate(paragraphs):
        node_id = content_addressed_id(
            "node",
            f"canonical-merge|{target_deliverable_id}|{draft_sha}|{index}|{text}",
        )
        kind = str(provenance.get("kind") or "")
        node_type = (
            "entity" if kind == "source" else "question" if "question" in kind else "insight"
        )
        _insert_verified_node(
            con,
            node_id=node_id,
            label=text,
            node_type=node_type,
            metadata={
                **provenance,
                "origin": "engagement_merge_commit",
                "draft_document_id": draft_document_id,
                "draft_sha256": draft_sha,
            },
        )
        node_ids.append(node_id)
        prose_provenance[index] = [node_id]
        if node_id != parent_node_id:
            edge_id = content_addressed_id(
                "edge", f"{node_id}|derived_from|{parent_node_id}|{draft_sha}"
            )
            source_document_id = parent_asset_id if canonical_source_document is not None else None
            investigation_id = str(provenance.get("investigation_id") or f"merge_{draft_sha[:16]}")
            edge_metadata = json.dumps(
                {
                    "draft_document_id": draft_document_id,
                    "spawn_id": provenance.get("spawn_id"),
                    "region_id": provenance.get("region_id"),
                    "source_reference_ids": provenance.get("source_reference_ids", []),
                    "twin_note_ids": provenance.get("twin_note_ids", []),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            existing_edge = con.execute(
                "SELECT source_node_id, target_node_id, relation, source_document_id, "
                "source_tier, extraction_confidence, graph_scope, investigation_id, metadata "
                "FROM edges WHERE edge_id = ?",
                [edge_id],
            ).fetchone()
            expected_edge = (
                node_id,
                parent_node_id,
                "derived_from",
                source_document_id,
                3,
                1.0,
                "depth",
                investigation_id,
                edge_metadata,
            )
            if existing_edge is not None and tuple(existing_edge) != expected_edge:
                raise CanonicalMergeConflict("canonical edge identity collides with other state")
            if existing_edge is None:
                con.execute(
                    "INSERT INTO edges "
                    "(edge_id, source_node_id, target_node_id, relation, source_document_id, "
                    "source_tier, extraction_confidence, graph_scope, investigation_id, metadata) "
                    "VALUES (?, ?, ?, 'derived_from', ?, 3, 1.0, 'depth', ?, ?)",
                    [
                        edge_id,
                        node_id,
                        parent_node_id,
                        source_document_id,
                        investigation_id,
                        edge_metadata,
                    ],
                )

    section_id = content_addressed_id("sec", f"canonical-merge|{target_deliverable_id}|{draft_sha}")
    section_title = str(doc_model.get("title") or "Merged research")
    section_prose = "\n\n".join(text for text, _ in paragraphs)
    section_provenance = json.dumps(prose_provenance, sort_keys=True, separators=(",", ":"))
    next_index = con.execute(
        "SELECT COALESCE(MAX(section_index), -1) + 1 FROM deliverable_sections "
        "WHERE deliverable_id = ? AND section_id <> ?",
        [target_deliverable_id, section_id],
    ).fetchone()[0]
    existing_section = con.execute(
        "SELECT deliverable_id, parent_section_id, section_index, title, prose_text, "
        "prose_provenance "
        "FROM deliverable_sections WHERE section_id = ?",
        [section_id],
    ).fetchone()
    if existing_section is not None and tuple(existing_section) != (
        target_deliverable_id,
        None,
        int(next_index),
        section_title,
        section_prose,
        section_provenance,
    ):
        raise CanonicalMergeConflict("draft section identity collides with other state")
    if existing_section is None:
        insert_section(
            con,
            deliverable_id=target_deliverable_id,
            section_id=section_id,
            section_index=int(next_index),
            title=section_title,
            prose_text=section_prose,
            prose_provenance=prose_provenance,
        )

    for index, node_id in enumerate(node_ids):
        kind = str(paragraphs[index][1].get("kind") or "")
        block_kind = (
            "open_question" if "question" in kind else "claim" if kind == "source" else "insight"
        )
        legacy_block = con.execute(
            "SELECT block_index FROM section_blocks "
            "WHERE section_id = ? AND block_kind = ? AND block_id = ?",
            [section_id, block_kind, node_id],
        ).fetchone()
        if legacy_block is not None and legacy_block != (index,):
            raise CanonicalMergeConflict("legacy section block collides with other state")
        if legacy_block is None:
            con.execute(
                "INSERT INTO section_blocks "
                "(section_id, block_kind, block_id, block_index) VALUES (?, ?, ?, ?)",
                [section_id, block_kind, node_id, index],
            )
        outline_block_id = content_addressed_id(
            "oblk", f"canonical-merge|{target_deliverable_id}|{draft_sha}|{index}"
        )
        outline_metadata = json.dumps(
            {"origin": "canonical_merge_commit", "draft_sha256": draft_sha},
            sort_keys=True,
            separators=(",", ":"),
        )
        existing_outline = con.execute(
            "SELECT section_id, block_kind, provenance_kind, node_id, "
            "source_block_kind, source_block_id, content, block_index, cluster_id, metadata "
            "FROM outline_blocks WHERE outline_block_id = ?",
            [outline_block_id],
        ).fetchone()
        expected_outline = (
            section_id,
            block_kind,
            "graph_node",
            node_id,
            block_kind,
            node_id,
            None,
            index,
            None,
            outline_metadata,
        )
        if existing_outline is not None and tuple(existing_outline) != expected_outline:
            raise CanonicalMergeConflict("outline block identity collides with other state")
        if existing_outline is None:
            con.execute(
                "INSERT INTO outline_blocks "
                "(outline_block_id, section_id, block_kind, provenance_kind, node_id, "
                "source_block_kind, source_block_id, content, block_index, metadata) "
                "VALUES (?, ?, ?, 'graph_node', ?, ?, ?, NULL, ?, ?)",
                [
                    outline_block_id,
                    section_id,
                    block_kind,
                    node_id,
                    block_kind,
                    node_id,
                    index,
                    outline_metadata,
                ],
            )

    metadata_row = con.execute(
        "SELECT metadata FROM deliverables WHERE deliverable_id = ?",
        [target_deliverable_id],
    ).fetchone()
    metadata = _json(metadata_row[0] if metadata_row else None)
    metadata.update(
        {
            "reviewed_doc_model": doc_model,
        }
    )
    con.execute(
        "UPDATE deliverables SET metadata = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE deliverable_id = ?",
        [json.dumps(metadata, sort_keys=True, separators=(",", ":")), target_deliverable_id],
    )
    new_revision = _target_revision(con, target_deliverable_id)
    metadata.update(
        {
            "revision": new_revision,
            "previous_revision": old_revision,
            "last_draft_sha256": draft_sha,
            "last_merge_section_id": section_id,
            "last_merge_node_ids": node_ids,
            "last_draft_document_id": draft_document_id,
        }
    )
    con.execute(
        "UPDATE deliverables SET metadata = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE deliverable_id = ?",
        [json.dumps(metadata, sort_keys=True, separators=(",", ":")), target_deliverable_id],
    )
    return CanonicalMergeCommit(
        deliverable_id=target_deliverable_id,
        draft_document_id=draft_document_id,
        old_revision=old_revision,
        new_revision=new_revision,
        section_id=section_id,
        node_ids=tuple(node_ids),
        paragraph_count=len(paragraphs),
        draft_sha256=draft_sha,
    )


__all__ = [
    "CanonicalMergeCommit",
    "CanonicalMergeConflict",
    "canonical_deliverable_revision",
    "commit_reviewed_draft",
    "load_reviewed_document_model",
    "load_latest_reviewed_document_model",
]
