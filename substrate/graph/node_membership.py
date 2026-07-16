"""Investigation membership for globally content-addressed graph nodes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeInvestigationMembership:
    node_id: str
    investigation_id: str
    node_type: str
    owner_user_id: str | None
    origin_note_id: str | None


@dataclass(frozen=True)
class NodeInvestigationObservation:
    node_id: str
    investigation_id: str
    origin_note_id: str
    source_document_id: str | None


def ensure_membership(
    con,
    *,
    node_id: str,
    investigation_id: str,
    node_type: str,
    owner_user_id: str | None = None,
    origin_note_id: str | None = None,
) -> None:
    """Record an immutable membership, rejecting conflicting local identity."""
    node = con.execute(
        "SELECT node_type, owner_user_id FROM nodes WHERE node_id=?", [node_id]
    ).fetchone()
    if node is None or node[0] != node_type:
        raise RuntimeError("node investigation membership conflicts with graph node")
    if node[1] != owner_user_id:
        raise RuntimeError("node investigation membership conflicts with graph owner")
    con.execute(
        "INSERT INTO node_investigation_memberships "
        "(node_id, investigation_id, node_type, owner_user_id, origin_note_id) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (node_id, investigation_id) DO NOTHING",
        [node_id, investigation_id, node_type, owner_user_id, origin_note_id],
    )
    row = con.execute(
        "SELECT node_type, owner_user_id, origin_note_id "
        "FROM node_investigation_memberships WHERE node_id=? AND investigation_id=?",
        [node_id, investigation_id],
    ).fetchone()
    if row is None or row[0] != node_type:
        raise RuntimeError("node investigation membership conflicts with node kind")
    if row[1] != owner_user_id:
        raise RuntimeError("node investigation membership conflicts with owner")
    # ``origin_note_id`` is retained only as the Cycle 86 legacy-primary
    # pointer. Cycle 87 stores every occurrence in the observation relation.
    if row[2] is None and origin_note_id is not None:
        con.execute(
            "UPDATE node_investigation_memberships SET origin_note_id=? "
            "WHERE node_id=? AND investigation_id=? AND origin_note_id IS NULL",
            [origin_note_id, node_id, investigation_id],
        )


def membership_for(con, node_id: str, investigation_id: str) -> NodeInvestigationMembership | None:
    row = con.execute(
        "SELECT node_type, owner_user_id, origin_note_id "
        "FROM node_investigation_memberships WHERE node_id=? AND investigation_id=?",
        [node_id, investigation_id],
    ).fetchone()
    if row is None:
        return None
    return NodeInvestigationMembership(node_id, investigation_id, row[0], row[1], row[2])


def ensure_observation(
    con,
    *,
    node_id: str,
    investigation_id: str,
    origin_note_id: str | None,
    source_document_id: str | None,
) -> None:
    if origin_note_id is None:
        return
    if not origin_note_id.strip():
        raise ValueError("origin note id must not be empty")
    if membership_for(con, node_id, investigation_id) is None:
        raise RuntimeError("node observation requires investigation membership")
    con.execute(
        "INSERT INTO node_investigation_observations "
        "(node_id, investigation_id, origin_note_id, source_document_id) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (node_id, investigation_id, origin_note_id) DO NOTHING",
        [node_id, investigation_id, origin_note_id, source_document_id],
    )
    row = con.execute(
        "SELECT source_document_id FROM node_investigation_observations "
        "WHERE node_id=? AND investigation_id=? AND origin_note_id=?",
        [node_id, investigation_id, origin_note_id],
    ).fetchone()
    if row is None or row[0] != source_document_id:
        raise RuntimeError("node observation conflicts with source document")


def observation_for(
    con,
    node_id: str,
    investigation_id: str,
    origin_note_id: str | None = None,
) -> NodeInvestigationObservation | None:
    params: list[str] = [node_id, investigation_id]
    where = "node_id=? AND investigation_id=?"
    if origin_note_id is not None:
        where += " AND origin_note_id=?"
        params.append(origin_note_id)
    row = con.execute(
        "SELECT origin_note_id, source_document_id FROM node_investigation_observations "
        f"WHERE {where} ORDER BY created_at, origin_note_id LIMIT 1",
        params,
    ).fetchone()
    if row is None:
        return None
    return NodeInvestigationObservation(node_id, investigation_id, row[0], row[1])
