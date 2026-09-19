"""Immutable contributor credit evidence, deliberately separate from economics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from runtime.db_lock import LockedConnection

from .authority import InterviewAccountAuthority
from .consent import consent_state

BASIS = frozenset({"self_reported", "operator_verified", "contractual_record"})


class ContributorAttributionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ContributorAttribution:
    event_id: str
    project_id: str
    interview_id: str
    contributor_ref: str
    display_label: str
    evidence_basis: str
    evidence_ref: str
    consent_event_ids: tuple[str, ...]
    active: bool


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _request_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _validate(value: str, name: str, *, limit: int = 512) -> str:
    if (
        not isinstance(value, str) or not value or value != value.strip()
        or "\x00" in value or len(value.encode()) > limit
    ):
        raise ValueError(f"contributor {name} is invalid")
    return value


def _parent(
    con: Any, authority: InterviewAccountAuthority, *, project_id: str, interview_id: str
) -> None:
    row = con.execute(
        "SELECT 1 FROM interviews_authority WHERE account_digest = ? AND owner_user_id = ? "
        "AND project_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, project_id, interview_id],
    ).fetchone()
    if row is None:
        raise ValueError("interview contributor parent not found")


def _current_consent_evidence(
    con: Any, authority: InterviewAccountAuthority, *, interview_id: str
) -> tuple[str, ...]:
    if not {"record", "attribute"} <= consent_state(
        con, authority, interview_id=interview_id
    ):
        raise ContributorAttributionConflict(
            "record and attribute consent are currently required for contributor credit"
        )
    rows = con.execute(
        "SELECT event_id, scope, granted FROM (SELECT event_id, scope, granted, "
        "row_number() OVER (PARTITION BY scope ORDER BY recorded_at DESC, event_id DESC) ordinal "
        "FROM interview_consent_events WHERE account_digest = ? AND owner_user_id = ? "
        "AND interview_id = ?) ranked WHERE ordinal = 1 AND scope IN ('record','attribute') "
        "ORDER BY scope",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchall()
    if len(rows) != 2 or not all(bool(row[2]) for row in rows):
        raise ContributorAttributionConflict("contributor consent evidence is incomplete")
    return tuple(str(row[0]) for row in rows)


def _from_row(row: tuple[Any, ...], *, active: bool) -> ContributorAttribution:
    return ContributorAttribution(
        event_id=str(row[0]), project_id=str(row[1]), interview_id=str(row[2]),
        contributor_ref=str(row[3]), display_label=str(row[4]),
        evidence_basis=str(row[5]), evidence_ref=str(row[6]),
        consent_event_ids=tuple(json.loads(str(row[7]))),
        active=active,
    )


def _get_bind_event(
    con: Any, authority: InterviewAccountAuthority, *, event_id: str
) -> ContributorAttribution:
    row = con.execute(
        "SELECT b.event_id, b.project_id, b.interview_id, b.contributor_ref, "
        "b.display_label, b.evidence_basis, b.evidence_ref, b.consent_event_ids_json, "
        "NOT EXISTS (SELECT 1 FROM interview_contributor_attribution_events r "
        "WHERE r.account_digest = b.account_digest AND r.action = 'revoke' "
        "AND r.target_event_id = b.event_id) FROM interview_contributor_attribution_events b "
        "WHERE b.account_digest = ? AND b.owner_user_id = ? AND b.event_id = ? "
        "AND b.action = 'bind'",
        [authority.account_digest, authority.account_id, event_id],
    ).fetchone()
    if row is None:
        raise ContributorAttributionConflict("contributor binding event is missing")
    return _from_row(tuple(row[:8]), active=bool(row[8]))


def get_active_attribution(
    con: Any,
    authority: InterviewAccountAuthority,
    *,
    project_id: str,
    interview_id: str,
    require_current_consent: bool = True,
) -> ContributorAttribution | None:
    _parent(con, authority, project_id=project_id, interview_id=interview_id)
    row = con.execute(
        "SELECT b.event_id, b.project_id, b.interview_id, b.contributor_ref, "
        "b.display_label, b.evidence_basis, b.evidence_ref, b.consent_event_ids_json "
        "FROM interview_contributor_attribution_events b WHERE b.account_digest = ? "
        "AND b.owner_user_id = ? AND b.project_id = ? AND b.interview_id = ? "
        "AND b.action = 'bind' AND NOT EXISTS (SELECT 1 FROM "
        "interview_contributor_attribution_events r WHERE r.account_digest = b.account_digest "
        "AND r.action = 'revoke' AND r.target_event_id = b.event_id) "
        "ORDER BY b.created_at DESC, b.event_id DESC LIMIT 1",
        [authority.account_digest, authority.account_id, project_id, interview_id],
    ).fetchone()
    if row is None:
        return None
    attribution = _from_row(tuple(row), active=True)
    if require_current_consent:
        _current_consent_evidence(con, authority, interview_id=interview_id)
        for event_id in attribution.consent_event_ids:
            if con.execute(
                "SELECT 1 FROM interview_consent_events WHERE account_digest = ? "
                "AND owner_user_id = ? AND interview_id = ? AND event_id = ? AND granted = TRUE",
                [authority.account_digest, authority.account_id, interview_id, event_id],
            ).fetchone() is None:
                raise ContributorAttributionConflict(
                    "frozen contributor consent evidence is missing"
                )
    return attribution


def record_attribution(
    con: LockedConnection,
    authority: InterviewAccountAuthority,
    *,
    project_id: str,
    interview_id: str,
    command_id: str,
    contributor_ref: str,
    display_label: str,
    evidence_basis: Literal["self_reported", "operator_verified", "contractual_record"],
    evidence_ref: str,
) -> ContributorAttribution:
    if not isinstance(con, LockedConnection):
        raise TypeError("contributor attribution requires a LockedConnection")
    _parent(con, authority, project_id=project_id, interview_id=interview_id)
    command_id = _validate(command_id, "command_id")
    contributor_ref = _validate(contributor_ref, "reference")
    display_label = _validate(display_label, "display label", limit=500)
    evidence_ref = _validate(evidence_ref, "evidence reference", limit=2048)
    if evidence_basis not in BASIS:
        raise ValueError("contributor evidence basis is invalid")
    request = _request_json({
        "action": "bind", "project_id": project_id, "interview_id": interview_id,
        "contributor_ref": contributor_ref, "display_label": display_label,
        "evidence_basis": evidence_basis, "evidence_ref": evidence_ref,
    })
    request_sha = _sha(request)
    replay = con.execute(
        "SELECT request_sha256, event_id FROM interview_contributor_attribution_events "
        "WHERE account_digest = ? AND owner_user_id = ? AND command_id = ?",
        [authority.account_digest, authority.account_id, command_id],
    ).fetchone()
    if replay is not None:
        if str(replay[0]) != request_sha:
            raise ContributorAttributionConflict(
                "contributor command was reused with different input"
            )
        # Idempotency is not a historical disclosure capability.  Replays return
        # the original temporal result only while current contributor consent
        # still permits this identity-bearing projection.
        _current_consent_evidence(con, authority, interview_id=interview_id)
        return _get_bind_event(con, authority, event_id=str(replay[1]))
    if get_active_attribution(
        con, authority, project_id=project_id, interview_id=interview_id,
        require_current_consent=False,
    ) is not None:
        raise ContributorAttributionConflict("interview already has an active contributor binding")
    consent_ids = _current_consent_evidence(con, authority, interview_id=interview_id)
    event_id = f"ivca-{_sha(authority.account_digest + chr(0) + command_id + chr(0) + request_sha)[:32]}"
    owns_transaction = not con.transaction_active
    if owns_transaction:
        con.execute("BEGIN TRANSACTION")
    try:
        con.execute(
            "INSERT INTO interview_contributor_attribution_events "
            "(event_id, account_digest, project_id, interview_id, owner_user_id, command_id, "
            "request_sha256, action, contributor_ref, display_label, evidence_basis, "
            "evidence_ref, consent_event_ids_json) VALUES (?, ?, ?, ?, ?, ?, ?, 'bind', "
            "?, ?, ?, ?, ?)",
            [event_id, authority.account_digest, project_id, interview_id,
             authority.account_id, command_id, request_sha, contributor_ref, display_label,
             evidence_basis, evidence_ref, json.dumps(consent_ids)],
        )
        if owns_transaction:
            con.execute("COMMIT")
    except BaseException:
        if owns_transaction:
            con.execute("ROLLBACK")
        raise
    result = get_active_attribution(
        con, authority, project_id=project_id, interview_id=interview_id
    )
    if result is None:
        raise ContributorAttributionConflict("contributor binding did not become active")
    return result


def revoke_attribution(
    con: LockedConnection,
    authority: InterviewAccountAuthority,
    *,
    project_id: str,
    interview_id: str,
    command_id: str,
    target_event_id: str,
) -> str:
    if not isinstance(con, LockedConnection):
        raise TypeError("contributor attribution requires a LockedConnection")
    _parent(con, authority, project_id=project_id, interview_id=interview_id)
    command_id = _validate(command_id, "command_id")
    target_event_id = _validate(target_event_id, "target event")
    request_sha = _sha(_request_json({
        "action": "revoke", "project_id": project_id, "interview_id": interview_id,
        "target_event_id": target_event_id,
    }))
    replay = con.execute(
        "SELECT request_sha256, event_id FROM interview_contributor_attribution_events "
        "WHERE account_digest = ? AND owner_user_id = ? AND command_id = ?",
        [authority.account_digest, authority.account_id, command_id],
    ).fetchone()
    if replay is not None:
        if str(replay[0]) != request_sha:
            raise ContributorAttributionConflict(
                "contributor command was reused with different input"
            )
        return str(replay[1])
    active = get_active_attribution(
        con, authority, project_id=project_id, interview_id=interview_id,
        require_current_consent=False,
    )
    if active is None or active.event_id != target_event_id:
        raise ContributorAttributionConflict("target contributor binding is not active")
    event_id = f"ivcr-{_sha(authority.account_digest + chr(0) + command_id + chr(0) + request_sha)[:32]}"
    con.execute(
        "INSERT INTO interview_contributor_attribution_events "
        "(event_id, account_digest, project_id, interview_id, owner_user_id, command_id, "
        "request_sha256, action, target_event_id, consent_event_ids_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'revoke', ?, '[]')",
        [event_id, authority.account_digest, project_id, interview_id, authority.account_id,
         command_id, request_sha, target_event_id],
    )
    return event_id


__all__ = [
    "ContributorAttribution", "ContributorAttributionConflict", "get_active_attribution",
    "record_attribution", "revoke_attribution",
]
