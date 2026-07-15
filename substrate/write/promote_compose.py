"""Promote one immutable research compose into a zero-spend Write workspace."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from runtime.db_lock import LockedConnection, connect_write
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.ops import insert_deliverable, insert_section
from substrate.graph.schema import ANTIEK_GRAPH_SCHEMA_V16_COMPOSE_WRITE_SQL
from substrate.research_artifact import compose_lock, load_compose_draft, parse_body_from_html
from substrate.research_artifact.paths import compose_member_path

from .outline_block import place_block

DeliverableKind = Literal[
    "research_memo", "book_chapter", "biography_section",
    "investor_brief", "general_essay",
]
ComposeBlockKind = Literal["insight", "open_question", "claim"]


class ComposeIntegrityError(ValueError):
    """The persisted compose no longer matches its immutable manifest."""


@dataclass(frozen=True)
class ComposeWriteResult:
    compose_id: str
    deliverable_id: str
    section_id: str
    snapshot_occurrence_count: int
    unique_block_count: int
    duplicate_count: int
    kind_conflict_count: int
    dangling_count: int
    member_count: int
    reused: bool


def _validated_occurrences(compose_id: str) -> tuple[str, int, list[tuple[str, str]]]:
    """Read and validate every snapshot before a DB connection is opened."""
    try:
        compose = load_compose_draft(compose_id)
    except FileNotFoundError:
        raise
    except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise ComposeIntegrityError("invalid compose manifest") from exc
    if compose.selection_fingerprint is None:
        raise ComposeIntegrityError("compose selection fingerprint is missing")

    occurrences: list[tuple[str, str]] = []
    for index, member in enumerate(compose.members):
        try:
            body = parse_body_from_html(
                compose_member_path(compose_id, index).read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ComposeIntegrityError(f"compose member {index} is missing or invalid") from exc
        if body.investigation_id != member.investigation_id:
            raise ComposeIntegrityError(f"compose member {index} investigation does not match manifest")
        if body.content_hash() != member.content_hash:
            raise ComposeIntegrityError(f"compose member {index} content hash does not match manifest")
        occurrences.extend((item.node_id, "insight") for item in body.insights)
        occurrences.extend((item.node_id, "open_question") for item in body.open_questions)

    fingerprint_payload = {
        "schema_version": 1,
        "members": [[m.investigation_id, m.content_hash] for m in compose.members],
    }
    raw = json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(raw.encode()).hexdigest() != compose.selection_fingerprint:
        raise ComposeIntegrityError("compose selection fingerprint does not match manifest")
    expected_id = f"cmp-{compose.selection_fingerprint[:24]}"
    if compose_id != expected_id:
        raise ComposeIntegrityError("compose id does not match selection fingerprint")
    return compose.selection_fingerprint, len(compose.members), occurrences


def promote_compose_to_write(
    compose_id: str,
    *,
    title: str | None = None,
    deliverable_kind: DeliverableKind = "research_memo",
    db_path: str | None = None,
) -> ComposeWriteResult:
    """Create or reuse the compose's one Write workspace.

    Snapshot parsing and hash validation complete before any write. Inside the
    single-writer lock, an explicit transaction owns the mapping, deliverable,
    section, and blocks so failure leaves no partial workspace.
    """
    # Validation and mapping commit share the filesystem lock with deletion,
    # so the immutable compose exists for the entire promotion boundary.
    with compose_lock():
        return _promote_locked(
            compose_id, title=title, deliverable_kind=deliverable_kind,
            db_path=db_path,
        )


def _promote_locked(
    compose_id: str,
    *,
    title: str | None,
    deliverable_kind: DeliverableKind,
    db_path: str | None,
) -> ComposeWriteResult:
    fingerprint, member_count, occurrences = _validated_occurrences(compose_id)

    first_kinds: dict[str, str] = {}
    ordered_node_ids: list[str] = []
    conflicting_node_ids: set[str] = set()
    for node_id, kind in occurrences:
        first = first_kinds.get(node_id)
        if first is None:
            first_kinds[node_id] = kind
            ordered_node_ids.append(node_id)
        elif first != kind:
            conflicting_node_ids.add(node_id)
    kind_conflicts = len(conflicting_node_ids)

    path = db_path or default_db_path()
    ensure_initialized(path)
    with connect_write(path, purpose="write/promote_compose") as con:
        # Existing databases may take ensure_initialized's warm fast path.
        con.execute(ANTIEK_GRAPH_SCHEMA_V16_COMPOSE_WRITE_SQL)
        con.execute("BEGIN TRANSACTION")
        try:
            existing = con.execute(
                "SELECT deliverable_id, section_id, selection_fingerprint "
                "FROM artifact_compose_write_workspaces WHERE compose_id = ?",
                [compose_id],
            ).fetchone()
            if existing is not None:
                if existing[2] != fingerprint:
                    raise ComposeIntegrityError("stored compose mapping fingerprint differs")
                dangling = _dangling_count(con, ordered_node_ids)
                con.execute("COMMIT")
                return _result(
                    compose_id, existing[0], existing[1], occurrences,
                    ordered_node_ids, kind_conflicts, dangling, member_count, True,
                )

            live_types = _live_types(con, ordered_node_ids)
            did = insert_deliverable(
                con,
                title=(title.strip() if title and title.strip() else f"Writing from {member_count} researches"),
                deliverable_kind=deliverable_kind,
                investigation_root_id=None,
                metadata={
                    "promoted_from": "artifact_compose",
                    "source_compose_id": compose_id,
                    "selection_fingerprint": fingerprint,
                    "investigation_root_reason": "multi-root immutable compose",
                    "ordering": "manifest member order, then first snapshot occurrence",
                },
            )
            sid = insert_section(con, deliverable_id=did, section_index=0, title="Reviewed sources")
            for index, node_id in enumerate(ordered_node_ids):
                block_kind = _block_kind(live_types.get(node_id), first_kinds[node_id])
                place_block(
                    con,
                    section_id=sid,
                    block_kind=block_kind,
                    provenance_kind="graph_node",
                    node_id=node_id,
                    block_index=index,
                    deliverable_id=did,
                    metadata={"source_compose_id": compose_id, "snapshot_kind": first_kinds[node_id]},
                    emit_event=False,
                )
            con.execute(
                "INSERT INTO artifact_compose_write_workspaces "
                "(compose_id, selection_fingerprint, deliverable_id, section_id) VALUES (?, ?, ?, ?)",
                [compose_id, fingerprint, did, sid],
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    # Per-block JSONL cannot commit atomically with DuckDB. This bulk bridge
    # therefore uses its normalized mapping and block metadata as the durable,
    # retry-safe lineage authority instead of claiming partial event history.
    dangling = len(ordered_node_ids) - len(live_types)
    return _result(
        compose_id, did, sid, occurrences, ordered_node_ids,
        kind_conflicts, dangling, member_count, False,
    )


def _live_types(con: LockedConnection, node_ids: list[str]) -> dict[str, str]:
    if not node_ids:
        return {}
    placeholders = ", ".join("?" for _ in node_ids)
    rows = con.execute(
        f"SELECT node_id, node_type FROM nodes WHERE node_id IN ({placeholders})",
        node_ids,
    ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def _dangling_count(con: LockedConnection, node_ids: list[str]) -> int:
    return len(node_ids) - len(_live_types(con, node_ids))


def _block_kind(live_type: str | None, snapshot_kind: str) -> ComposeBlockKind:
    if live_type == "question":
        return "open_question"
    if live_type == "claim":
        return "claim"
    if live_type == "insight":
        return "insight"
    if live_type is None and snapshot_kind == "open_question":
        return "open_question"
    return "insight"


def _result(
    compose_id: str, did: str, sid: str, occurrences: list[tuple[str, str]],
    unique_ids: list[str], kind_conflicts: int, dangling: int,
    member_count: int, reused: bool,
) -> ComposeWriteResult:
    return ComposeWriteResult(
        compose_id=compose_id,
        deliverable_id=did,
        section_id=sid,
        snapshot_occurrence_count=len(occurrences),
        unique_block_count=len(unique_ids),
        duplicate_count=len(occurrences) - len(unique_ids),
        kind_conflict_count=kind_conflicts,
        dangling_count=dangling,
        member_count=member_count,
        reused=reused,
    )
