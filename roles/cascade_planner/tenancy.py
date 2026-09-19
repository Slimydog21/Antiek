"""Account-authorized mutable cascade plans with graph projection."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import duckdb

from runtime.db_lock import LockedConnection
from substrate.event_log import log_event_authorized
from substrate.graph.insight_question import promote_question_authorized
from substrate.graph.ops import insert_edge_authorized
from substrate.investigation_tenancy import InvestigationAuthority

from .persist import TREE_RELATION
from .tree_contract import PlanNode, PlanTree


class PlanAuthorityDenied(RuntimeError):
    pass


class LaunchAttemptConflict(RuntimeError):
    pass


class LaunchAttemptUnknown(RuntimeError):
    def __init__(self, session_id: str):
        super().__init__("cascade launch outcome is unknown")
        self.session_id = session_id


def _serialized(tree: PlanTree) -> tuple[str, str]:
    encoded = json.dumps(
        tree.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


def plan_tree_fingerprint(tree: PlanTree) -> str:
    """Exact persisted-tree fingerprint used for conditional launch claims."""
    return _serialized(tree)[1]


def _project_node(
    con: LockedConnection,
    authority: InvestigationAuthority,
    node: PlanNode,
    embedding_provider: Any,
) -> str:
    node_id = promote_question_authorized(
        authority,
        text=node.question,
        con=con,
        embedding_provider=embedding_provider,
        metadata={"cascade_plan": True, "plan_local_id": node.local_id},
    )
    node.graph_node_id = node_id
    for child in node.children:
        child_id = _project_node(con, authority, child, embedding_provider)
        insert_edge_authorized(
            con,
            authority,
            source_node_id=node_id,
            target_node_id=child_id,
            relation=TREE_RELATION,
            source_tier=3,
            extraction_confidence=1.0,
            graph_scope="depth",
            metadata={"cascade_plan": True},
            on_conflict="ignore",
        )
    return node_id


def save_plan_authorized(
    con: LockedConnection,
    authority: InvestigationAuthority,
    tree: PlanTree,
    *,
    embedding_provider: Any,
) -> str:
    """Project immutable questions, then store owner-scoped mutable plan state."""
    if not isinstance(con, LockedConnection):
        raise TypeError("authorized plan persistence requires a LockedConnection")
    root_node_id = _project_node(con, authority, tree.root, embedding_provider)
    tree.root_investigation_id = authority.investigation_id
    encoded, fingerprint = _serialized(tree)
    identity = [authority.account_digest, authority.investigation_digest]
    rows = con.execute(
        "SELECT plan_id FROM cascade_plan_authority "
        "WHERE account_digest = ? AND investigation_digest = ?",
        identity,
    ).fetchall()
    if not rows:
        con.execute(
            "INSERT INTO cascade_plan_authority "
            "(account_digest, investigation_digest, plan_id, graph_root_node_id, "
            "tree_json, tree_fingerprint) VALUES (?, ?, ?, ?, ?, ?)",
            [*identity, authority.investigation_id, root_node_id, encoded, fingerprint],
        )
    elif rows == [(authority.investigation_id,)]:
        con.execute(
            "UPDATE cascade_plan_authority SET graph_root_node_id = ?, tree_json = ?, "
            "tree_fingerprint = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE account_digest = ? AND investigation_digest = ?",
            [root_node_id, encoded, fingerprint, *identity],
        )
    else:
        raise PlanAuthorityDenied("cascade plan authority conflicts with stored state")
    return authority.investigation_id


def load_plan_authorized(
    con: Any, authority: InvestigationAuthority
) -> PlanTree | None:
    rows = con.execute(
        "SELECT plan_id, tree_json, tree_fingerprint FROM cascade_plan_authority "
        "WHERE account_digest = ? AND investigation_digest = ?",
        [authority.account_digest, authority.investigation_digest],
    ).fetchall()
    if not rows:
        return None
    if len(rows) != 1 or rows[0][0] != authority.investigation_id:
        raise PlanAuthorityDenied("cascade plan authority is invalid")
    encoded, fingerprint = rows[0][1], rows[0][2]
    if (
        not isinstance(encoded, str)
        or not isinstance(fingerprint, str)
        or hashlib.sha256(encoded.encode()).hexdigest() != fingerprint
    ):
        raise PlanAuthorityDenied("cascade plan state failed integrity validation")
    try:
        document = json.loads(encoded)
        tree = PlanTree.from_dict(document)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise PlanAuthorityDenied("cascade plan state is malformed") from exc
    if tree.root_investigation_id != authority.investigation_id:
        raise PlanAuthorityDenied("cascade plan state has foreign identity")
    return tree


def approve_plan_authorized(
    con: LockedConnection,
    authority: InvestigationAuthority,
    *,
    approver: str,
    embedding_provider: Any,
) -> dict[str, Any]:
    tree = load_plan_authorized(con, authority)
    if tree is None:
        raise PlanAuthorityDenied("cascade plan not found")
    tree.approval.state = "approved"
    tree.approval.approved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    tree.approval.approved_by = approver
    save_plan_authorized(con, authority, tree, embedding_provider=embedding_provider)
    log_event_authorized(
        authority,
        "plan.approved",
        payload={
            "plan_id": authority.investigation_id,
            "plan_version": tree.approval.plan_version,
        },
        role="user_agent",
    )
    return tree.approval.to_dict()


def is_plan_launchable_authorized(con: Any, authority: InvestigationAuthority) -> bool:
    tree = load_plan_authorized(con, authority)
    return tree is not None and tree.approval.is_launchable


def claim_plan_launch_authorized(
    con: LockedConnection,
    plan_authority: InvestigationAuthority,
    launch_authority: InvestigationAuthority,
    *,
    expected_tree_fingerprint: str | None = None,
) -> PlanTree:
    """Atomically freeze one approved plan version for one unique launch."""
    if not isinstance(con, LockedConnection):
        raise TypeError("authorized launch claim requires a LockedConnection")
    if plan_authority.account_id != launch_authority.account_id:
        raise PlanAuthorityDenied("cascade launch authority is invalid")
    tree = load_plan_authorized(con, plan_authority)
    if tree is None or not tree.approval.is_launchable:
        raise PlanAuthorityDenied("cascade plan is not launchable")
    encoded, fingerprint = _serialized(tree)
    if expected_tree_fingerprint is not None and fingerprint != expected_tree_fingerprint:
        raise PlanAuthorityDenied("cascade plan changed after launch review")
    try:
        con.execute(
            "INSERT INTO cascade_plan_launch_authority "
            "(account_digest, plan_investigation_digest, launch_investigation_digest, "
            "plan_id, session_id, plan_version, tree_json, tree_fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                plan_authority.account_digest,
                plan_authority.investigation_digest,
                launch_authority.investigation_digest,
                plan_authority.investigation_id,
                launch_authority.investigation_id,
                tree.approval.plan_version,
                encoded,
                fingerprint,
            ],
        )
    except duckdb.ConstraintException as exc:
        raise PlanAuthorityDenied("cascade launch claim conflicts with stored state") from exc
    return tree


def is_plan_launch_claim_authorized(
    con: Any,
    plan_authority: InvestigationAuthority,
    launch_authority: InvestigationAuthority,
) -> bool:
    if plan_authority.account_id != launch_authority.account_id:
        return False
    rows = con.execute(
        "SELECT plan_id, session_id, tree_json, tree_fingerprint "
        "FROM cascade_plan_launch_authority WHERE account_digest = ? "
        "AND plan_investigation_digest = ? AND launch_investigation_digest = ?",
        [
            plan_authority.account_digest,
            plan_authority.investigation_digest,
            launch_authority.investigation_digest,
        ],
    ).fetchall()
    if len(rows) != 1:
        return False
    plan_id, session_id, encoded, fingerprint = rows[0]
    return (
        plan_id == plan_authority.investigation_id
        and session_id == launch_authority.investigation_id
        and isinstance(encoded, str)
        and isinstance(fingerprint, str)
        and hashlib.sha256(encoded.encode()).hexdigest() == fingerprint
    )


def claim_launch_attempt_authorized(
    con: LockedConnection,
    plan_authority: InvestigationAuthority,
    *,
    idempotency_key: str,
    request_fingerprint: str,
    proposed_session_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """Claim one owner/plan/operator attempt or replay its completed response.

    The raw operator key is never persisted. A claimed row is deliberately
    non-retriable: after a process crash the server cannot prove whether a
    provider saw dispatch, so automatic redispatch would risk duplicate spend.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError("authorized launch-attempt claim requires a LockedConnection")
    key_digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
    identity = [
        plan_authority.account_digest,
        plan_authority.investigation_digest,
        key_digest,
    ]
    rows = con.execute(
        "SELECT plan_id, session_id, request_fingerprint, state, response_json, "
        "response_fingerprint "
        "FROM cascade_launch_attempts WHERE account_digest = ? "
        "AND plan_investigation_digest = ? AND idempotency_key_digest = ?",
        identity,
    ).fetchall()
    if not rows:
        con.execute(
            "INSERT INTO cascade_launch_attempts "
            "(account_digest, plan_investigation_digest, idempotency_key_digest, "
            "plan_id, session_id, request_fingerprint, state) "
            "VALUES (?, ?, ?, ?, ?, ?, 'claimed')",
            [
                *identity,
                plan_authority.investigation_id,
                proposed_session_id,
                request_fingerprint,
            ],
        )
        return proposed_session_id, None
    if len(rows) != 1:
        raise LaunchAttemptConflict("cascade launch-attempt authority is invalid")
    (
        plan_id,
        session_id,
        stored_fingerprint,
        state,
        response_json,
        response_fingerprint,
    ) = rows[0]
    if plan_id != plan_authority.investigation_id or stored_fingerprint != request_fingerprint:
        raise LaunchAttemptConflict("Idempotency-Key was already used for another launch")
    if state == "claimed":
        raise LaunchAttemptUnknown(str(session_id))
    if (
        state != "completed"
        or not isinstance(response_json, str)
        or not isinstance(response_fingerprint, str)
        or hashlib.sha256(response_json.encode()).hexdigest() != response_fingerprint
    ):
        raise LaunchAttemptConflict("cascade launch-attempt state is invalid")
    try:
        response = json.loads(response_json)
    except json.JSONDecodeError as exc:
        raise LaunchAttemptConflict("cascade launch-attempt response is malformed") from exc
    if not isinstance(response, dict) or response.get("session_id") != session_id:
        raise LaunchAttemptConflict("cascade launch-attempt response failed integrity validation")
    return str(session_id), response


def complete_launch_attempt_authorized(
    con: LockedConnection,
    plan_authority: InvestigationAuthority,
    *,
    idempotency_key: str,
    request_fingerprint: str,
    session_id: str,
    response: dict[str, Any],
) -> None:
    """Atomically seal the exact response for durable, zero-dispatch replay."""
    if not isinstance(con, LockedConnection):
        raise TypeError("authorized launch-attempt completion requires a LockedConnection")
    if response.get("session_id") != session_id:
        raise LaunchAttemptConflict("launch response does not match claimed session")
    key_digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
    encoded = json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    response_fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    result = con.execute(
        "UPDATE cascade_launch_attempts SET state = 'completed', response_json = ?, "
        "response_fingerprint = ?, "
        "completed_at = CURRENT_TIMESTAMP WHERE account_digest = ? "
        "AND plan_investigation_digest = ? AND idempotency_key_digest = ? "
        "AND plan_id = ? AND session_id = ? AND request_fingerprint = ? "
        "AND state = 'claimed' RETURNING state",
        [
            encoded,
            response_fingerprint,
            plan_authority.account_digest,
            plan_authority.investigation_digest,
            key_digest,
            plan_authority.investigation_id,
            session_id,
            request_fingerprint,
        ],
    )
    row = result.fetchone()
    if row != ("completed",):
        raise LaunchAttemptConflict("cascade launch-attempt completion conflicts with stored state")


def read_launch_attempt_authorized(
    con: LockedConnection | duckdb.DuckDBPyConnection,
    plan_authority: InvestigationAuthority,
    *,
    idempotency_key: str,
) -> dict[str, Any] | None:
    """Read durable attempt truth without claiming, completing, or dispatching."""
    if not isinstance(con, (LockedConnection, duckdb.DuckDBPyConnection)):
        raise TypeError("authorized launch-attempt read requires a database connection")
    key_digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
    rows = con.execute(
        "SELECT plan_id, session_id, request_fingerprint, state, response_json, "
        "response_fingerprint FROM cascade_launch_attempts "
        "WHERE account_digest = ? AND plan_investigation_digest = ? "
        "AND idempotency_key_digest = ?",
        [
            plan_authority.account_digest,
            plan_authority.investigation_digest,
            key_digest,
        ],
    ).fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise LaunchAttemptConflict("cascade launch-attempt authority is invalid")
    plan_id, session_id, request_fingerprint, state, response_json, response_fingerprint = rows[0]
    if plan_id != plan_authority.investigation_id or state not in {"claimed", "completed"}:
        raise LaunchAttemptConflict("cascade launch-attempt state is invalid")
    if not all(isinstance(value, str) and value for value in (session_id, request_fingerprint)):
        raise LaunchAttemptConflict("cascade launch-attempt identity is invalid")
    response_integrity: bool | None = None
    if state == "completed":
        if (
            not isinstance(response_json, str)
            or not isinstance(response_fingerprint, str)
            or hashlib.sha256(response_json.encode()).hexdigest() != response_fingerprint
        ):
            raise LaunchAttemptConflict("cascade launch-attempt response failed integrity validation")
        try:
            response = json.loads(response_json)
        except json.JSONDecodeError as exc:
            raise LaunchAttemptConflict("cascade launch-attempt response is malformed") from exc
        if not isinstance(response, dict) or response.get("session_id") != session_id:
            raise LaunchAttemptConflict("cascade launch-attempt response failed integrity validation")
        response_integrity = True
    elif response_json is not None or response_fingerprint is not None:
        raise LaunchAttemptConflict("claimed launch attempt contains an invalid response")
    return {
        "plan_id": str(plan_id),
        "session_id": str(session_id),
        "state": str(state),
        "response_integrity": response_integrity,
    }
