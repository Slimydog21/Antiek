"""Account-memory writes and owner-scoped reads over the canonical graph.

A memory is a subject node pointing to a ``memory`` node through an owner-scoped,
bi-temporal edge. Writing a new object for the same ``(owner, subject,
predicate)`` inserts a new node/edge, then closes the old edge by setting
``valid_until`` and ``superseded_by``. No row is deleted.

The caller supplies the existing :class:`~runtime.db_lock.LockedConnection`;
this module never opens a DuckDB connection.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import JsonValue

from runtime.db_lock import LockedConnection
from substrate.graph.ops import content_addressed_id, insert_edge, insert_node
from substrate.schemas import GraphEdgeInsertedPayload, GraphNodeInsertedPayload
from substrate.write.event_outbox import (
    build_typed_envelope,
    dispatch_pending_best_effort,
    enqueue_event,
)

from .models import MemoryItem

_GRAPH_SCOPE: Literal["depth"] = "depth"
_MEMORY_METADATA_SCHEMA = "antiek.account-memory.v1"


class MemoryStoreError(RuntimeError):
    """A memory record could not be represented without losing its contract."""


def write_memory_item(
    con: LockedConnection,
    *,
    owner_user_id: str,
    subject: str,
    predicate: str,
    object: str,
    provenance: Mapping[str, JsonValue],
    valid_from: datetime,
) -> MemoryItem:
    """Write one memory and invalidate any current value for the same key.

    Repeating an already-current ``(owner, subject, predicate, object)`` is an
    idempotent read-back. A changed object is a new version: the prior edge is
    retained with ``valid_to`` set to this item's ``valid_from``. This operation
    owns its transaction so a caller cannot catch an error and later commit a
    partial projection.
    """
    _assert_locked(con)
    if con.in_explicit_transaction:
        raise RuntimeError("write_memory_item manages its own transaction")

    owner = _required_text(owner_user_id, "owner_user_id")
    memory_subject = _required_text(subject, "subject")
    memory_predicate = _required_text(predicate, "predicate")
    memory_object = _required_text(object, "object")
    start = _naive_utc(valid_from)
    provenance_json = _normalized_provenance(provenance)
    investigation_id = _provenance_text(provenance_json, "investigation_id")
    if investigation_id is None:
        investigation_id = _first_source_reference(provenance_json)
    chunk_id = _provenance_text(provenance_json, "chunk_id")
    source_document_id = _validate_chunk_document(
        con,
        chunk_id=chunk_id,
        source_document_id=_source_document_id(provenance_json),
    )
    source_tier = _source_tier(provenance_json)
    extraction_confidence = _extraction_confidence(provenance_json)

    subject_node_id = content_addressed_id(
        "memory-subject", _canonical_json([owner, memory_subject])
    )
    memory_id = content_addressed_id(
        "memory",
        _canonical_json(
            [owner, memory_subject, memory_predicate, memory_object, provenance_json, start]
        ),
    )
    edge_id = content_addressed_id("memory-edge", memory_id)

    con.execute("BEGIN")
    try:
        current = _current_rows(
            con,
            owner_user_id=owner,
            subject=memory_subject,
            predicate=memory_predicate,
        )
        for row in current:
            if str(row[5]) == memory_object:
                item = _row_to_item(row)
                pending_investigation = _provenance_text(
                    item.provenance, "investigation_id"
                ) or _first_source_reference(item.provenance)
                con.execute("COMMIT")
                dispatch_pending_best_effort(con, pending_investigation)
                return item

        if current and start <= max(_row_valid_from(row) for row in current):
            raise ValueError(
                "valid_from must be later than the current memory version"
            )

        subject_was_present = _row_exists(con, "nodes", "node_id", subject_node_id)
        memory_was_present = _row_exists(con, "nodes", "node_id", memory_id)
        edge_was_present = _row_exists(con, "edges", "edge_id", edge_id)
        if edge_was_present:
            raise MemoryStoreError("an invalidated memory version cannot be reactivated")

        insert_node(
            con,
            node_id=subject_node_id,
            canonical_label=memory_subject,
            node_type="entity",
            graph_scope=_GRAPH_SCOPE,
            investigation_id=investigation_id,
            owner_user_id=owner,
            metadata={"schema": _MEMORY_METADATA_SCHEMA, "role": "subject"},
            on_conflict="ignore",
            emit_event=False,
        )
        _assert_subject_identity(con, subject_node_id, owner, memory_subject)

        node_metadata = {
            "schema": _MEMORY_METADATA_SCHEMA,
            "subject": memory_subject,
            "predicate": memory_predicate,
            "object": memory_object,
            "provenance": provenance_json,
        }
        insert_node(
            con,
            node_id=memory_id,
            canonical_label=memory_object,
            node_type="memory",
            graph_scope=_GRAPH_SCOPE,
            investigation_id=investigation_id,
            owner_user_id=owner,
            metadata=node_metadata,
            on_conflict="ignore",
            emit_event=False,
        )
        _assert_memory_identity(con, memory_id, owner, node_metadata)

        insert_edge(
            con,
            edge_id=edge_id,
            source_node_id=subject_node_id,
            target_node_id=memory_id,
            relation=memory_predicate,
            chunk_id=chunk_id,
            source_document_id=source_document_id,
            source_tier=source_tier,
            extraction_confidence=extraction_confidence,
            valid_from=start,
            graph_scope=_GRAPH_SCOPE,
            investigation_id=investigation_id,
            metadata={"schema": _MEMORY_METADATA_SCHEMA},
            owner_user_id=owner,
            on_conflict="ignore",
            emit_event=False,
        )

        if current:
            old_edge_ids = [str(row[1]) for row in current]
            placeholders = ", ".join("?" for _ in old_edge_ids)
            con.execute(
                "UPDATE edges SET valid_until = ?, superseded_by = ? "
                f"WHERE edge_id IN ({placeholders}) AND owner_user_id = ? "
                "AND valid_until IS NULL",
                [start, edge_id, *old_edge_ids, owner],
            )

        written_row = _memory_row(con, owner_user_id=owner, edge_id=edge_id)
        if written_row is None:
            raise MemoryStoreError("memory write did not produce a readable graph edge")
        item = _row_to_item(written_row)
        _enqueue_insert_events(
            con,
            investigation_id=investigation_id,
            owner_user_id=owner,
            subject_node_id=subject_node_id,
            subject=memory_subject,
            subject_was_present=subject_was_present,
            memory_id=memory_id,
            memory_object=memory_object,
            memory_was_present=memory_was_present,
            edge_id=edge_id,
            predicate=memory_predicate,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
            source_tier=source_tier,
            extraction_confidence=extraction_confidence,
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    dispatch_pending_best_effort(con, investigation_id)
    return item


def list_memory(
    con: LockedConnection,
    owner_user_id: str,
    *,
    subject: str | None = None,
    predicate: str | None = None,
    include_invalidated: bool = False,
    valid_at: datetime | None = None,
    limit: int | None = None,
) -> list[MemoryItem]:
    """List memory for exactly one owner, newest-valid first.

    Current items are returned by default. ``include_invalidated=True`` exposes
    the preserved history; ``valid_at`` instead selects the interval that was
    valid at one point in time.
    """
    _assert_locked(con)
    owner = _required_text(owner_user_id, "owner_user_id")
    conditions = [
        "e.owner_user_id = ?",
        "s.owner_user_id = ?",
        "m.owner_user_id = ?",
        "m.node_type = 'memory'",
    ]
    params: list[object] = [owner, owner, owner]
    if subject is not None:
        conditions.append("s.canonical_label = ?")
        params.append(_required_text(subject, "subject"))
    if predicate is not None:
        conditions.append("e.relation = ?")
        params.append(_required_text(predicate, "predicate"))
    if valid_at is not None:
        point = _naive_utc(valid_at)
        conditions.extend(["e.valid_from <= ?", "(e.valid_until IS NULL OR e.valid_until > ?)"])
        params.extend([point, point])
    elif not include_invalidated:
        point = datetime.now(UTC).replace(tzinfo=None)
        conditions.extend(["e.valid_from <= ?", "(e.valid_until IS NULL OR e.valid_until > ?)"])
        params.extend([point, point])
    limit_sql = ""
    if limit is not None:
        if isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        limit_sql = " LIMIT ?"
        params.append(limit)
    rows = con.execute(
        _SELECT_MEMORY
        + " WHERE "
        + " AND ".join(conditions)
        + " ORDER BY e.valid_from DESC, e.extracted_at DESC, e.edge_id"
        + limit_sql,
        params,
    ).fetchall()
    return [_row_to_item(row) for row in rows]


_SELECT_MEMORY = """
SELECT
    m.node_id,
    e.edge_id,
    e.owner_user_id,
    s.canonical_label,
    e.relation,
    m.canonical_label,
    m.metadata,
    e.valid_from,
    e.valid_until,
    e.superseded_by,
    e.extracted_at
FROM edges e
JOIN nodes s ON s.node_id = e.source_node_id
JOIN nodes m ON m.node_id = e.target_node_id
"""


def _current_rows(
    con: LockedConnection, *, owner_user_id: str, subject: str, predicate: str
) -> list[tuple[object, ...]]:
    return cast(
        list[tuple[object, ...]],
        con.execute(
            _SELECT_MEMORY
            + " WHERE e.owner_user_id = ? AND s.owner_user_id = ? "
            "AND m.owner_user_id = ? AND m.node_type = 'memory' "
            "AND s.canonical_label = ? AND e.relation = ? "
            "AND e.valid_until IS NULL ORDER BY e.valid_from DESC, e.edge_id",
            [owner_user_id, owner_user_id, owner_user_id, subject, predicate],
        ).fetchall(),
    )


def _memory_row(
    con: LockedConnection, *, owner_user_id: str, edge_id: str
) -> tuple[object, ...] | None:
    return cast(
        tuple[object, ...] | None,
        con.execute(
            _SELECT_MEMORY
            + " WHERE e.edge_id = ? AND e.owner_user_id = ? "
            "AND s.owner_user_id = ? AND m.owner_user_id = ? "
            "AND m.node_type = 'memory'",
            [edge_id, owner_user_id, owner_user_id, owner_user_id],
        ).fetchone(),
    )


def _row_valid_from(row: tuple[object, ...]) -> datetime:
    value = row[7]
    if not isinstance(value, datetime):
        raise MemoryStoreError("memory edge valid_from is not a timestamp")
    return value


def _row_exists(
    con: LockedConnection, table: str, id_column: str, identity: str
) -> bool:
    if (table, id_column) not in {("nodes", "node_id"), ("edges", "edge_id")}:
        raise ValueError("unsupported memory identity lookup")
    return (
        con.execute(
            f"SELECT 1 FROM {table} WHERE {id_column} = ? LIMIT 1", [identity]
        ).fetchone()
        is not None
    )


def _enqueue_insert_events(
    con: LockedConnection,
    *,
    investigation_id: str,
    owner_user_id: str,
    subject_node_id: str,
    subject: str,
    subject_was_present: bool,
    memory_id: str,
    memory_object: str,
    memory_was_present: bool,
    edge_id: str,
    predicate: str,
    source_document_id: str | None,
    chunk_id: str | None,
    source_tier: int,
    extraction_confidence: float,
) -> None:
    """Persist graph-admission event intents in the graph transaction."""
    if not subject_was_present:
        event = build_typed_envelope(
            investigation_id,
            GraphNodeInsertedPayload(
                node_id=subject_node_id,
                canonical_label=subject,
                node_type="entity",
                graph_scope=_GRAPH_SCOPE,
                has_embedding=False,
            ),
            role="connector",
            event_id=f"evt-account-memory-node-{subject_node_id}",
        )
        enqueue_event(
            con,
            operation_id=f"account-memory-node-insert:{subject_node_id}",
            aggregate_kind="account_memory_node",
            aggregate_id=subject_node_id,
            event=event,
        )
    if not memory_was_present:
        event = build_typed_envelope(
            investigation_id,
            GraphNodeInsertedPayload(
                node_id=memory_id,
                canonical_label=memory_object,
                node_type="memory",
                graph_scope=_GRAPH_SCOPE,
                has_embedding=False,
            ),
            role="connector",
            event_id=f"evt-account-memory-node-{memory_id}",
        )
        enqueue_event(
            con,
            operation_id=f"account-memory-node-insert:{memory_id}",
            aggregate_kind="account_memory_node",
            aggregate_id=memory_id,
            event=event,
        )
    event = build_typed_envelope(
        investigation_id,
        GraphEdgeInsertedPayload(
            edge_id=edge_id,
            source_node_id=subject_node_id,
            target_node_id=memory_id,
            relation=predicate,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
            source_tier=source_tier,
            extraction_confidence=extraction_confidence,
            graph_scope=_GRAPH_SCOPE,
            owner_user_id=owner_user_id,
        ),
        role="connector",
        event_id=f"evt-account-memory-edge-{edge_id}",
    )
    enqueue_event(
        con,
        operation_id=f"account-memory-edge-insert:{edge_id}",
        aggregate_kind="account_memory_edge",
        aggregate_id=edge_id,
        event=event,
    )


def _row_to_item(row: tuple[object, ...]) -> MemoryItem:
    try:
        metadata = json.loads(str(row[6]))
        provenance = metadata["provenance"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MemoryStoreError("memory node metadata is not canonical") from exc
    if not isinstance(provenance, dict):
        raise MemoryStoreError("memory provenance is not an object")
    return MemoryItem.model_validate(
        {
            "memory_id": row[0],
            "edge_id": row[1],
            "owner_user_id": row[2],
            "subject": row[3],
            "predicate": row[4],
            "object": row[5],
            "provenance": provenance,
            "valid_from": row[7],
            "valid_to": row[8],
            "superseded_by": row[9],
            "created_at": row[10],
        }
    )


def _normalized_provenance(
    provenance: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    if not isinstance(provenance, Mapping):
        raise TypeError("provenance must be a mapping")
    value = dict(provenance)
    probe = MemoryItem(
        memory_id="probe",
        edge_id="probe",
        owner_user_id="probe",
        subject="probe",
        predicate="probe",
        object="probe",
        provenance=value,
        valid_from=datetime(1970, 1, 1),
        created_at=datetime(1970, 1, 1),
    )
    return probe.provenance


def _first_source_reference(provenance: Mapping[str, JsonValue]) -> str:
    preferred = (
        "source_ref",
        "source_document_id",
        "document_id",
        "chunk_id",
        "thread_id",
        "note_id",
        "event_id",
        "source_id",
        "investigation_id",
        "provenance_id",
        "id",
        "ref",
        "source",
    )
    for key in preferred:
        value = provenance.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("memory provenance must carry a source reference")


def _provenance_text(
    provenance: Mapping[str, JsonValue], key: str
) -> str | None:
    value = provenance.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"provenance {key} must be a non-blank string")
    return value.strip()


def _source_document_id(provenance: Mapping[str, JsonValue]) -> str | None:
    explicit = _provenance_text(provenance, "source_document_id")
    alias = _provenance_text(provenance, "document_id")
    if explicit is not None and alias is not None and explicit != alias:
        raise ValueError("provenance document references conflict")
    return explicit or alias


def _validate_chunk_document(
    con: LockedConnection, *, chunk_id: str | None, source_document_id: str | None
) -> str | None:
    if chunk_id is None:
        if source_document_id is not None and con.execute(
            "SELECT 1 FROM documents WHERE document_id = ?", [source_document_id]
        ).fetchone() is None:
            raise ValueError(
                f"provenance document {source_document_id!r} does not exist"
            )
        return source_document_id
    row = con.execute(
        "SELECT document_id FROM chunks WHERE chunk_id = ?", [chunk_id]
    ).fetchone()
    if row is None:
        raise ValueError(f"provenance chunk {chunk_id!r} does not exist")
    actual = str(row[0])
    if source_document_id is not None and source_document_id != actual:
        raise ValueError("provenance chunk does not belong to source document")
    return actual


def _source_tier(provenance: Mapping[str, JsonValue]) -> int:
    value = provenance.get("source_tier", 1)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError("provenance source_tier must be an integer from 1 to 5")
    return value


def _extraction_confidence(provenance: Mapping[str, JsonValue]) -> float:
    value = provenance.get("extraction_confidence", 1.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("provenance extraction_confidence must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError("provenance extraction_confidence must be from 0 to 1")
    return result


def _assert_subject_identity(
    con: LockedConnection, node_id: str, owner_user_id: str, subject: str
) -> None:
    row = con.execute(
        "SELECT canonical_label, node_type, owner_user_id FROM nodes WHERE node_id = ?",
        [node_id],
    ).fetchone()
    if row != (subject, "entity", owner_user_id):
        raise MemoryStoreError("memory subject node identity conflicts")


def _assert_memory_identity(
    con: LockedConnection,
    memory_id: str,
    owner_user_id: str,
    expected_metadata: Mapping[str, object],
) -> None:
    row = con.execute(
        "SELECT node_type, owner_user_id, metadata FROM nodes WHERE node_id = ?",
        [memory_id],
    ).fetchone()
    if row is None or row[0] != "memory" or row[1] != owner_user_id:
        raise MemoryStoreError("memory node identity conflicts")
    try:
        actual_metadata = json.loads(str(row[2]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MemoryStoreError("memory node metadata is invalid") from exc
    if actual_metadata != expected_metadata:
        raise MemoryStoreError("memory node metadata conflicts")


def _assert_locked(con: object) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "account memory requires a LockedConnection; acquire it through "
            "runtime.db_lock.connect_write"
        )


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be blank")
    return normalized


def _naive_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("valid_from must be a datetime")
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


__all__ = ["MemoryStoreError", "list_memory", "write_memory_item"]
