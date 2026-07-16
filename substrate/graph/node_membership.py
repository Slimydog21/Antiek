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
    if row[2] is not None and origin_note_id is not None and row[2] != origin_note_id:
        raise RuntimeError("node investigation membership conflicts with origin note")
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
