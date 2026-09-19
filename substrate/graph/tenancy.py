"""Non-activating graph authority allocation and private node membership."""

from __future__ import annotations

import hashlib
import hmac
import json
from enum import StrEnum

from runtime.db_lock import LockedConnection
from substrate.investigation_tenancy import InvestigationAuthority


class GraphAuthorityConflict(RuntimeError):
    pass


class GraphTenancyState(StrEnum):
    UNSCOPED = "unscoped"
    COPYING = "copying"
    SHADOW = "shadow"
    SCOPED = "scoped"
    QUARANTINED = "quarantined"


_TRANSITIONS = frozenset(
    {
        (GraphTenancyState.UNSCOPED, GraphTenancyState.COPYING),
        (GraphTenancyState.COPYING, GraphTenancyState.SHADOW),
        (GraphTenancyState.COPYING, GraphTenancyState.QUARANTINED),
        (GraphTenancyState.SHADOW, GraphTenancyState.SCOPED),
        (GraphTenancyState.SHADOW, GraphTenancyState.QUARANTINED),
        (GraphTenancyState.SCOPED, GraphTenancyState.SHADOW),
        (GraphTenancyState.QUARANTINED, GraphTenancyState.COPYING),
    }
)
_MEMBERSHIP_ROLES = frozenset({"insight", "question", "note", "claim", "reference"})


def _require_locked(con: object) -> LockedConnection:
    if not isinstance(con, LockedConnection):
        raise TypeError("graph tenancy operations require a LockedConnection")
    return con


def graph_key(authority: InvestigationAuthority) -> str:
    """Domain-separate graph identity from the accepted W3 stream key."""
    return hmac.new(
        bytes.fromhex(authority.stream_key),
        b"antiek-graph-authority-v1",
        hashlib.sha256,
    ).hexdigest()


def _manifest(con: LockedConnection) -> tuple[str, str] | None:
    rows = con.execute(
        "SELECT key_id, state FROM graph_tenancy_manifest "
        "WHERE singleton_key = 'graph-tenancy-v1'"
    ).fetchall()
    if len(rows) > 1:
        raise GraphAuthorityConflict("graph tenancy manifest is invalid")
    if not rows:
        return None
    key_id, state = rows[0]
    if not isinstance(key_id, str) or state not in set(GraphTenancyState):
        raise GraphAuthorityConflict("graph tenancy manifest is invalid")
    return key_id, state


def initialize_graph_authority(
    con: LockedConnection, authority: InvestigationAuthority
) -> str:
    """Bind one DB to the tenancy key and allocate an exact graph authority."""
    con = _require_locked(con)
    manifest = _manifest(con)
    if manifest is None:
        con.execute(
            "INSERT INTO graph_tenancy_manifest "
            "(singleton_key, version, key_id, state) VALUES (?, 1, ?, ?)",
            ["graph-tenancy-v1", authority.key_id, GraphTenancyState.UNSCOPED.value],
        )
    elif manifest[0] != authority.key_id:
        raise GraphAuthorityConflict("graph tenancy key does not match authority")
    elif manifest[1] == GraphTenancyState.QUARANTINED.value:
        raise GraphAuthorityConflict("graph tenancy is quarantined")

    expected = (
        authority.account_digest,
        authority.investigation_digest,
        graph_key(authority),
        authority.key_id,
    )
    rows = con.execute(
        "SELECT account_digest, investigation_digest, graph_key, key_id "
        "FROM graph_investigation_allocations "
        "WHERE account_digest = ? AND investigation_digest = ?",
        [authority.account_digest, authority.investigation_digest],
    ).fetchall()
    if not rows:
        con.execute(
            "INSERT INTO graph_investigation_allocations "
            "(account_digest, investigation_digest, graph_key, key_id) "
            "VALUES (?, ?, ?, ?)",
            list(expected),
        )
    elif len(rows) != 1 or tuple(rows[0]) != expected:
        raise GraphAuthorityConflict("graph investigation allocation is invalid")
    return expected[2]


def assert_graph_authority(
    con: LockedConnection, authority: InvestigationAuthority
) -> str:
    con = _require_locked(con)
    return _assert_graph_authority_connection(con, authority)


def assert_graph_authority_read(con: object, authority: InvestigationAuthority) -> str:
    """Validate authority on a read connection without acquiring a writer lock."""
    if not callable(getattr(con, "execute", None)):
        raise TypeError("graph tenancy reads require a database connection")
    key = _assert_graph_authority_connection(con, authority)
    manifest = _manifest(con)
    if manifest is None or manifest[1] not in {
        GraphTenancyState.SHADOW.value,
        GraphTenancyState.SCOPED.value,
    }:
        raise GraphAuthorityConflict("graph tenancy state denies scoped reads")
    return key


def _assert_graph_authority_connection(
    con: object, authority: InvestigationAuthority
) -> str:
    manifest = _manifest(con)
    if manifest is None or manifest[0] != authority.key_id:
        raise GraphAuthorityConflict("graph tenancy manifest does not match authority")
    if manifest[1] == GraphTenancyState.QUARANTINED.value:
        raise GraphAuthorityConflict("graph tenancy is quarantined")
    expected_key = graph_key(authority)
    rows = con.execute(
        "SELECT graph_key, key_id FROM graph_investigation_allocations "
        "WHERE account_digest = ? AND investigation_digest = ?",
        [authority.account_digest, authority.investigation_digest],
    ).fetchall()
    if rows != [(expected_key, authority.key_id)]:
        raise GraphAuthorityConflict("graph investigation authority is not allocated")
    return expected_key


def graph_tenancy_state(con: LockedConnection) -> GraphTenancyState:
    con = _require_locked(con)
    manifest = _manifest(con)
    if manifest is None:
        raise GraphAuthorityConflict("graph tenancy manifest is not initialized")
    return GraphTenancyState(manifest[1])


def transition_graph_tenancy_state(
    con: LockedConnection,
    *,
    expected: GraphTenancyState,
    desired: GraphTenancyState,
) -> None:
    con = _require_locked(con)
    if (expected, desired) not in _TRANSITIONS:
        raise ValueError("unsupported graph tenancy transition")
    if graph_tenancy_state(con) is not expected:
        raise GraphAuthorityConflict("graph tenancy state changed")
    con.execute(
        "UPDATE graph_tenancy_manifest SET state = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE singleton_key = 'graph-tenancy-v1' AND state = ?",
        [desired.value, expected.value],
    )
    if graph_tenancy_state(con) is not desired:
        raise GraphAuthorityConflict("graph tenancy state transition failed")


def add_node_membership(
    con: LockedConnection,
    authority: InvestigationAuthority,
    *,
    node_id: str,
    role: str,
    source_row_digest: str,
    metadata: dict[str, object] | None = None,
) -> None:
    con = _require_locked(con)
    assert_graph_authority(con, authority)
    if not isinstance(node_id, str) or not node_id or node_id != node_id.strip():
        raise ValueError("graph membership node id is invalid")
    if role not in _MEMBERSHIP_ROLES:
        raise ValueError("graph membership role is invalid")
    if (
        not isinstance(source_row_digest, str)
        or len(source_row_digest) != 64
        or any(character not in "0123456789abcdef" for character in source_row_digest)
    ):
        raise ValueError("graph membership source digest is invalid")
    metadata_json = json.dumps(
        metadata or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    identity = [
        authority.account_digest,
        authority.investigation_digest,
        node_id,
        role,
    ]
    rows = con.execute(
        "SELECT source_row_digest, membership_metadata "
        "FROM investigation_node_memberships "
        "WHERE account_digest = ? AND investigation_digest = ? "
        "AND node_id = ? AND role = ?",
        identity,
    ).fetchall()
    if not rows:
        con.execute(
            "INSERT INTO investigation_node_memberships "
            "(account_digest, investigation_digest, node_id, role, "
            "source_row_digest, membership_metadata) VALUES (?, ?, ?, ?, ?, ?)",
            [*identity, source_row_digest, metadata_json],
        )
    elif rows != [(source_row_digest, metadata_json)]:
        raise GraphAuthorityConflict("graph membership conflicts with existing source")


def has_node_membership(
    con: LockedConnection,
    authority: InvestigationAuthority,
    *,
    node_id: str,
) -> bool:
    con = _require_locked(con)
    assert_graph_authority(con, authority)
    row = con.execute(
        "SELECT 1 FROM investigation_node_memberships "
        "WHERE account_digest = ? AND investigation_digest = ? AND node_id = ? "
        "LIMIT 1",
        [authority.account_digest, authority.investigation_digest, node_id],
    ).fetchone()
    return row is not None


def has_node_membership_read(
    con: object,
    authority: InvestigationAuthority,
    *,
    node_id: str,
) -> bool:
    assert_graph_authority_read(con, authority)
    row = con.execute(
        "SELECT 1 FROM investigation_node_memberships "
        "WHERE account_digest = ? AND investigation_digest = ? AND node_id = ? "
        "LIMIT 1",
        [authority.account_digest, authority.investigation_digest, node_id],
    ).fetchone()
    return row is not None
