"""Transactional outbox for confirmed twin graph-node events."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from runtime.db_lock import LockedConnection, connect_write
from substrate.event_log import emit_typed_idempotent
from substrate.schemas.events import GraphNodeInsertedPayload


def ensure_promotion_outbox(con: LockedConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS twin_promotion_event_outbox (
            event_id TEXT PRIMARY KEY,
            investigation_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            emitted BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )


def promotion_event_id(
    *, owner_id: str, session_id: str, preview_sha256: str, node_id: str
) -> str:
    material = (
        f"antiek.twin-promotion.graph-event.v1\0{owner_id}\0{session_id}\0"
        f"{preview_sha256}\0{node_id}"
    ).encode()
    return f"evt-tpr-{hashlib.sha256(material).hexdigest()[:24]}"


def stage_promoted_node_event(
    con: LockedConnection,
    *,
    event_id: str,
    investigation_id: str,
    node_id: str,
    canonical_label: str,
    node_type: str,
    has_embedding: bool,
) -> None:
    payload = {
        "node_id": node_id,
        "canonical_label": canonical_label,
        "node_type": node_type,
        "graph_scope": "depth",
        "has_embedding": has_embedding,
    }
    con.execute(
        "INSERT INTO twin_promotion_event_outbox "
        "(event_id, investigation_id, payload_json) VALUES (?, ?, ?) "
        "ON CONFLICT DO NOTHING",
        [event_id, investigation_id, json.dumps(payload, sort_keys=True)],
    )


def flush_promotion_outbox(db_path: str, *, events_dir: str | None) -> int:
    """Emit pending rows idempotently, then mark them delivered."""
    con = connect_write(db_path, purpose="flush_twin_promotion_event_outbox")
    emitted = 0
    try:
        ensure_promotion_outbox(con)
        rows = con.execute(
            "SELECT event_id, investigation_id, payload_json "
            "FROM twin_promotion_event_outbox WHERE emitted = FALSE ORDER BY event_id"
        ).fetchall()
        for event_id, investigation_id, payload_json in rows:
            raw: dict[str, Any] = json.loads(payload_json)
            payload = GraphNodeInsertedPayload(**raw)
            emit_typed_idempotent(
                event_id,
                investigation_id,
                payload,
                role="connector",
                events_dir=events_dir,
            )
            con.execute(
                "UPDATE twin_promotion_event_outbox SET emitted = TRUE WHERE event_id = ?",
                [event_id],
            )
            emitted += 1
        return emitted
    finally:
        con.close()

