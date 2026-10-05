"""Owner action escrow and provider attempts in the existing BYOT database.

These records describe accounting inputs, not authentication or permission to
send. The caller must derive owner/body/route facts at its real admission and
final transport boundaries. Model-record limits are not provider key credit.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, TypeVar

if TYPE_CHECKING:
    from substrate.byot_usage.ledger import OperationRow

MAX_MONEY = (1 << 63) - 1
_Published = TypeVar("_Published")
ACTIVE_STATES = "('allocated','prepared','sent','settlement_pending','unknown')"
RlmWorkflow = Literal[
    "long_document_wrestling", "long_corpus_synthesis", "investigation",
    "repl_query", "repl_batch", "dag_planning", "dag_execution", "equipped_batch",
]
_WORKFLOWS = frozenset({
    "long_document_wrestling", "long_corpus_synthesis", "investigation",
    "repl_query", "repl_batch", "dag_planning", "dag_execution", "equipped_batch",
})
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@+\-]{0,255}\Z")


def checked_int(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_MONEY:
        raise ValueError("accounting integer is invalid")
    return value


def checked_sum(values: Iterator[int] | list[int] | tuple[int, ...]) -> int:
    return checked_int(sum(checked_int(value) for value in values))


def _identity(value: object) -> None:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError("accounting identity is invalid")


def _digest(value: object) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError("accounting digest is invalid")


def _text(value: object, maximum: int) -> None:
    if type(value) is not str or len(value.encode("utf-8")) > maximum:
        raise ValueError("accounting result is invalid")


@dataclass(frozen=True, slots=True)
class ApprovedOwnerRoute:
    user_model_id: str
    provider_id: str
    model_id: str
    route_digest: str

    def __post_init__(self) -> None:
        for value in (self.user_model_id, self.provider_id, self.model_id):
            _identity(value)
        _digest(self.route_digest)


@dataclass(frozen=True, slots=True)
class OwnerActionDecision:
    owner_user_id: str
    action_id: str
    action_kind: RlmWorkflow
    budget_cents: int
    body_authority_digest: str
    owner_decision_digest: str
    approved_routes: tuple[ApprovedOwnerRoute, ...]

    def __post_init__(self) -> None:
        _identity(self.owner_user_id)
        _identity(self.action_id)
        if type(self.action_kind) is not str or self.action_kind not in _WORKFLOWS:
            raise ValueError("action workflow is invalid")
        checked_int(self.budget_cents)
        _digest(self.body_authority_digest)
        _digest(self.owner_decision_digest)
        if type(self.approved_routes) is not tuple or not 1 <= len(self.approved_routes) <= 64:
            raise ValueError("approved routes are invalid")
        for route in self.approved_routes:
            if type(route) is not ApprovedOwnerRoute:
                raise ValueError("approved route is invalid")
        if len(set(self.approved_routes)) != len(self.approved_routes):
            raise ValueError("approved routes are duplicated")


@dataclass(frozen=True, slots=True)
class OwnerActionRef:
    owner_user_id: str
    action_id: str
    epoch: int

    def __post_init__(self) -> None:
        _identity(self.owner_user_id)
        _identity(self.action_id)
        checked_int(self.epoch)


@dataclass(frozen=True, slots=True)
class AttemptProposal:
    operation_id: str
    user_model_id: str
    provider_id: str
    model_id: str
    route_digest: str
    authority_digest: str
    rate_limit_digest: str
    reserved_cents: int
    action_epoch: int
    parent_operation_id: str | None = None
    native_session_id: str | None = None
    attempt_kind: Literal["canonical", "prime_root", "prime_child"] = "canonical"

    def __post_init__(self) -> None:
        for value in (self.operation_id, self.user_model_id, self.provider_id, self.model_id):
            _identity(value)
        for value in (self.route_digest, self.authority_digest, self.rate_limit_digest):
            _digest(value)
        checked_int(self.reserved_cents)
        checked_int(self.action_epoch)
        for optional in (self.parent_operation_id, self.native_session_id):
            if optional is not None:
                _identity(optional)
        if self.parent_operation_id == self.operation_id:
            raise ValueError("attempt cannot parent itself")
        if self.attempt_kind not in ("canonical", "prime_root", "prime_child"):
            raise ValueError("attempt kind is invalid")


@dataclass(frozen=True, slots=True)
class FinalSendFacts:
    request_digest: str
    authority_digest: str
    route_digest: str
    rate_limit_digest: str
    body_authority_digest: str
    claim_nonce_digest: str
    action_epoch: int

    def __post_init__(self) -> None:
        for value in (
            self.request_digest, self.authority_digest, self.route_digest,
            self.rate_limit_digest, self.body_authority_digest, self.claim_nonce_digest,
        ):
            _digest(value)
        checked_int(self.action_epoch)


@dataclass(frozen=True, slots=True)
class VerifiedAttemptFacts:
    provider_id: str
    model_id: str
    provider_attempt_event_id: str
    evidence_sha256: str
    request_digest: str
    cost_micro_usd: int
    result_reference: str = ""
    result_text: str = ""

    def __post_init__(self) -> None:
        for value in (self.provider_id, self.model_id, self.provider_attempt_event_id):
            _identity(value)
        _digest(self.evidence_sha256)
        _digest(self.request_digest)
        checked_int(self.cost_micro_usd)
        _text(self.result_reference, 1024)
        _text(self.result_text, 1_048_576)

    @property
    def actual_cents(self) -> int:
        return (self.cost_micro_usd + 9999) // 10000


@dataclass(frozen=True, slots=True)
class ActionSnapshot:
    decision: OwnerActionDecision
    epoch: int
    state: Literal["open", "closing", "closed", "quarantined"]
    settled_cents: int
    reserved_cents: int
    available_cents: int
    owner_held_cents: int
    projection_pending: int
    quarantined: bool

    @property
    def ref(self) -> OwnerActionRef:
        return OwnerActionRef(self.decision.owner_user_id, self.decision.action_id, self.epoch)

    @property
    def action_id(self) -> str:
        return self.decision.action_id

    @property
    def budget_cents(self) -> int:
        return self.decision.budget_cents


@dataclass(frozen=True, slots=True)
class ActionAttemptSnapshot:
    operation: OperationRow
    proposal: AttemptProposal
    request_digest: str | None
    claim_nonce_digest: str | None
    cost_micro_usd: int | None
    result_reference: str | None


@dataclass(frozen=True, slots=True)
class AttemptClaim:
    won: bool
    attempt: ActionAttemptSnapshot


@dataclass(frozen=True, slots=True)
class OwnerPolicySnapshot:
    owner_user_id: str
    limit_cents: int | None
    revision: int


@dataclass(frozen=True, slots=True)
class OwnerUsageSnapshot:
    owner_user_id: str
    used_cents: int
    held_cents: int
    limit_cents: int | None
    policy_revision: int

    @property
    def available_cents(self) -> int | None:
        if self.limit_cents is None:
            return None
        return max(0, self.limit_cents - self.used_cents - self.held_cents)


@dataclass(frozen=True, slots=True)
class OwnerAttemptEvent:
    journal_id: str
    sequence: int
    owner_user_id: str
    action_id: str
    operation_id: str
    user_model_id: str
    provider_id: str
    model_id: str
    authority_digest: str
    request_digest: str
    evidence_sha256: str
    provider_attempt_event_id: str
    cost_micro_usd: int
    actual_cents: int
    occurred_at: str
    digest: str = ""

    @property
    def event_kind(self) -> Literal["settled"]:
        return "settled"

    def canonical_payload(self) -> str:
        return json.dumps({
            "schema": "byot-owner-attempt-settled-v1", "event_kind": self.event_kind,
            "journal_id": self.journal_id, "sequence": self.sequence,
            "owner_user_id": self.owner_user_id, "action_id": self.action_id,
            "operation_id": self.operation_id, "user_model_id": self.user_model_id,
            "provider_id": self.provider_id, "model_id": self.model_id,
            "authority_digest": self.authority_digest, "request_digest": self.request_digest,
            "evidence_sha256": self.evidence_sha256,
            "provider_attempt_event_id": self.provider_attempt_event_id,
            "cost_micro_usd": self.cost_micro_usd, "actual_cents": self.actual_cents,
            "occurred_at": self.occurred_at,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def __post_init__(self) -> None:
        for value in (
            self.journal_id, self.owner_user_id, self.action_id, self.operation_id,
            self.user_model_id, self.provider_id, self.model_id, self.provider_attempt_event_id,
        ):
            _identity(value)
        checked_int(self.sequence, minimum=1)
        checked_int(self.cost_micro_usd)
        checked_int(self.actual_cents)
        if self.actual_cents != (self.cost_micro_usd + 9999) // 10000:
            raise ValueError("event charge differs from usage")
        for value in (self.authority_digest, self.request_digest, self.evidence_sha256):
            _digest(value)
        if type(self.occurred_at) is not str:
            raise ValueError("event timestamp is invalid")
        occurred = datetime.fromisoformat(self.occurred_at)
        if occurred.tzinfo is None or occurred.utcoffset() != UTC.utcoffset(occurred):
            raise ValueError("event timestamp is invalid")
        calculated = hashlib.sha256(self.canonical_payload().encode()).hexdigest()
        if self.digest:
            _digest(self.digest)
        elif type(self.digest) is str:
            object.__setattr__(self, "digest", calculated)
        else:
            raise ValueError("event digest is invalid")
        if self.digest != calculated:
            raise ValueError("event digest differs from facts")


ACTION_COLUMNS = {
    "action_id": "TEXT", "parent_operation_id": "TEXT", "native_session_id": "TEXT",
    "attempt_kind": "TEXT", "route_digest": "TEXT", "rate_limit_digest": "TEXT",
    "action_epoch": "INTEGER", "request_digest": "TEXT", "claim_nonce_digest": "TEXT",
    "cost_micro_usd": "INTEGER", "result_reference": "TEXT",
}
ACTION_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS byot_owner_policy (owner_user_id TEXT PRIMARY KEY,"
    " limit_cents INTEGER CHECK(limit_cents >= 0), revision INTEGER NOT NULL CHECK(revision >= 1),"
    " updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS byot_action_journal (owner_user_id TEXT NOT NULL,"
    " action_id TEXT NOT NULL, action_kind TEXT NOT NULL, budget_cents INTEGER NOT NULL"
    " CHECK(budget_cents >= 0), body_authority_digest TEXT NOT NULL,"
    " owner_decision_digest TEXT NOT NULL, epoch INTEGER NOT NULL CHECK(epoch >= 0),"
    " state TEXT NOT NULL CHECK(state IN ('open','closing','closed','quarantined')),"
    " quarantined INTEGER NOT NULL DEFAULT 0 CHECK(quarantined IN (0,1)),"
    " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
    " PRIMARY KEY(owner_user_id,action_id))",
    "CREATE TABLE IF NOT EXISTS byot_action_routes (owner_user_id TEXT NOT NULL,"
    " action_id TEXT NOT NULL, ordinal INTEGER NOT NULL, user_model_id TEXT NOT NULL,"
    " provider_id TEXT NOT NULL, model_id TEXT NOT NULL, route_digest TEXT NOT NULL,"
    " PRIMARY KEY(owner_user_id,action_id,ordinal),"
    " FOREIGN KEY(owner_user_id,action_id) REFERENCES byot_action_journal(owner_user_id,action_id))",
    "CREATE TABLE IF NOT EXISTS byot_action_outbox (sequence INTEGER PRIMARY KEY AUTOINCREMENT,"
    " owner_user_id TEXT NOT NULL, action_id TEXT NOT NULL, operation_id TEXT NOT NULL,"
    " occurred_at TEXT NOT NULL, digest TEXT NOT NULL, acknowledged_at TEXT,"
    " UNIQUE(owner_user_id,operation_id),"
    " FOREIGN KEY(owner_user_id,action_id) REFERENCES byot_action_journal(owner_user_id,action_id))",
    "CREATE INDEX IF NOT EXISTS byot_operation_action_state ON"
    " byot_operation_journal(owner_user_id,action_id,state)",
    "CREATE INDEX IF NOT EXISTS byot_operation_record_state ON"
    " byot_operation_journal(owner_user_id,api_key_id,state)",
    "CREATE UNIQUE INDEX IF NOT EXISTS byot_attempt_claim_nonce ON"
    " byot_operation_journal(claim_nonce_digest) WHERE claim_nonce_digest IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS byot_attempt_provider_event ON"
    " byot_operation_journal(owner_user_id,provider_id,dispatch_event_id)"
    " WHERE action_id IS NOT NULL AND dispatch_event_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS byot_outbox_pending ON"
    " byot_action_outbox(acknowledged_at,sequence)",
    "CREATE TABLE IF NOT EXISTS byot_owned_wrestling_job ("
    " owner_user_id TEXT NOT NULL, action_id TEXT NOT NULL,"
    " investigation_id TEXT NOT NULL UNIQUE, document_id TEXT NOT NULL,"
    " source_reference TEXT NOT NULL, source_digest TEXT NOT NULL,"
    " request_event_id TEXT NOT NULL UNIQUE, delivered_event_id TEXT NOT NULL UNIQUE,"
    " request_payload_digest TEXT NOT NULL, state TEXT NOT NULL"
    " CHECK(state IN ('queued','running','ready','delivered','unresolved','refused')),"
    " canonical_input_reference TEXT, canonical_input_digest TEXT,"
    " result_reference TEXT, result_digest TEXT, execution_token TEXT,"
    " updated_at TEXT NOT NULL,"
    " PRIMARY KEY(owner_user_id,action_id),"
    " FOREIGN KEY(owner_user_id,action_id) REFERENCES byot_action_journal(owner_user_id,action_id))",
    "CREATE TABLE IF NOT EXISTS byot_owned_wrestling_outbox ("
    " owner_user_id TEXT NOT NULL, action_id TEXT NOT NULL,"
    " event_kind TEXT NOT NULL CHECK(event_kind IN ('requested','delivered')) ,"
    " event_id TEXT NOT NULL UNIQUE, payload_digest TEXT NOT NULL,"
    " published_at TEXT, PRIMARY KEY(owner_user_id,action_id,event_kind),"
    " FOREIGN KEY(owner_user_id,action_id) REFERENCES byot_owned_wrestling_job(owner_user_id,action_id))",
)


@dataclass(frozen=True, slots=True)
class OwnedWrestlingJob:
    owner_user_id: str
    action_id: str
    investigation_id: str
    document_id: str
    source_reference: str
    source_digest: str
    request_event_id: str
    delivered_event_id: str
    request_payload_digest: str
    state: str
    canonical_input_reference: str | None
    canonical_input_digest: str | None
    result_reference: str | None
    result_digest: str | None
    execution_token: str | None


def _owned_job(con: sqlite3.Connection, owner: str, action_id: str) -> OwnedWrestlingJob | None:
    row = con.execute(
        "SELECT owner_user_id,action_id,investigation_id,document_id,source_reference,"
        "source_digest,request_event_id,delivered_event_id,request_payload_digest,state,"
        "canonical_input_reference,canonical_input_digest,result_reference,result_digest,"
        "execution_token"
        " FROM byot_owned_wrestling_job"
        " WHERE owner_user_id=? AND action_id=?", (owner, action_id),
    ).fetchone()
    return OwnedWrestlingJob(*row) if row else None


def record_exposure(con: sqlite3.Connection, owner: str, record: str) -> int:
    usage = con.execute(
        "SELECT used_cents FROM byot_key_usage WHERE owner_user_id=? AND api_key_id=?",
        (owner, record),
    ).fetchone()
    holds = con.execute(
        "SELECT MAX(reserved_cents,COALESCE(actual_cents,0)) FROM byot_operation_journal"
        f" WHERE owner_user_id=? AND api_key_id=? AND state IN {ACTIVE_STATES}",
        (owner, record),
    ).fetchall()
    return checked_sum([usage[0] if usage else 0, *(row[0] for row in holds)])


class _OwnerActionAccounting:
    """Action methods using only ByotUsageLedger's connection and money rows."""

    def _connect(self) -> sqlite3.Connection:
        raise NotImplementedError

    @contextmanager
    def _action_transaction(self, *, write: bool = True) -> Iterator[sqlite3.Connection]:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def _action_snapshot(
        self, con: sqlite3.Connection, owner: str, action_id: str,
    ) -> ActionSnapshot | None:
        row = con.execute(
            "SELECT action_kind,budget_cents,body_authority_digest,owner_decision_digest,"
            " epoch,state,quarantined FROM byot_action_journal"
            " WHERE owner_user_id=? AND action_id=?", (owner, action_id),
        ).fetchone()
        if row is None:
            return None
        routes = con.execute(
            "SELECT user_model_id,provider_id,model_id,route_digest FROM byot_action_routes"
            " WHERE owner_user_id=? AND action_id=? ORDER BY ordinal", (owner, action_id),
        ).fetchall()
        decision = OwnerActionDecision(owner, action_id, row[0], row[1], row[2], row[3],
                                       tuple(ApprovedOwnerRoute(*route) for route in routes))
        charges = con.execute(
            "SELECT actual_cents FROM byot_operation_journal"
            " WHERE owner_user_id=? AND action_id=? AND state='settled'", (owner, action_id),
        ).fetchall()
        holds = con.execute(
            "SELECT MAX(reserved_cents,COALESCE(actual_cents,0)) FROM byot_operation_journal"
            f" WHERE owner_user_id=? AND action_id=? AND state IN {ACTIVE_STATES}",
            (owner, action_id),
        ).fetchall()
        settled = checked_sum([charge[0] for charge in charges])
        reserved = checked_sum([hold[0] for hold in holds])
        remainder = max(0, decision.budget_cents - settled)
        held = remainder if row[5] == "open" else reserved
        if row[5] == "quarantined":
            held = max(remainder, reserved)
        pending = con.execute(
            "SELECT COUNT(*) FROM byot_action_outbox WHERE owner_user_id=? AND action_id=?"
            " AND acknowledged_at IS NULL", (owner, action_id),
        ).fetchone()[0]
        return ActionSnapshot(decision, row[4], row[5], settled, reserved,
                              max(0, remainder - reserved) if row[5] == "open" else 0,
                              held, pending, bool(row[6]))

    def _require_action(
        self, con: sqlite3.Connection, owner: str, action_id: str,
    ) -> ActionSnapshot:
        from substrate.byot_usage.ledger import OperationConflict

        action = self._action_snapshot(con, owner, action_id)
        if action is None:
            raise OperationConflict("owner action is unavailable")
        return action

    def action(self, owner: str, action_id: str) -> ActionSnapshot | None:
        _identity(owner)
        _identity(action_id)
        with self._action_transaction(write=False) as con:
            return self._action_snapshot(con, owner, action_id)

    def _owner_usage(self, con: sqlite3.Connection, owner: str) -> OwnerUsageSnapshot:
        policy = con.execute(
            "SELECT limit_cents,revision FROM byot_owner_policy WHERE owner_user_id=?", (owner,),
        ).fetchone()
        used = checked_sum([row[0] for row in con.execute(
            "SELECT used_cents FROM byot_key_usage WHERE owner_user_id=?", (owner,),
        )])
        holds = [row[0] for row in con.execute(
            "SELECT MAX(reserved_cents,COALESCE(actual_cents,0)) FROM byot_operation_journal"
            f" WHERE owner_user_id=? AND action_id IS NULL AND state IN {ACTIVE_STATES}", (owner,),
        )]
        for row in con.execute(
            "SELECT action_id FROM byot_action_journal WHERE owner_user_id=?", (owner,),
        ).fetchall():
            holds.append(self._require_action(con, owner, row[0]).owner_held_cents)
        return OwnerUsageSnapshot(owner, used, checked_sum(holds),
                                  policy[0] if policy else None, policy[1] if policy else 0)

    def owner_usage(self, owner: str) -> OwnerUsageSnapshot:
        _identity(owner)
        with self._action_transaction(write=False) as con:
            return self._owner_usage(con, owner)

    def _admit_owner(self, con: sqlite3.Connection, owner: str, extra: int) -> None:
        from substrate.byot_usage.ledger import OperationConflict

        if con.execute(
            "SELECT 1 FROM byot_action_journal WHERE owner_user_id=?"
            " AND quarantined=1 AND state!='closed' LIMIT 1", (owner,),
        ).fetchone():
            raise OperationConflict("owner action liability requires reconciliation")
        usage = self._owner_usage(con, owner)
        exposure = checked_sum([usage.used_cents, usage.held_cents, extra])
        if usage.limit_cents is not None and exposure > usage.limit_cents:
            raise OperationConflict("operation exceeds local owner limit")

    def set_owner_limit(
        self, owner: str, limit_cents: int | None, *, expected_revision: int = 0,
    ) -> OwnerPolicySnapshot:
        from substrate.byot_usage.ledger import OperationConflict

        _identity(owner)
        if limit_cents is not None:
            checked_int(limit_cents)
        checked_int(expected_revision)
        with self._action_transaction() as con:
            row = con.execute(
                "SELECT revision FROM byot_owner_policy WHERE owner_user_id=?", (owner,),
            ).fetchone()
            if (row[0] if row else 0) != expected_revision:
                raise OperationConflict("owner policy revision changed")
            revision = checked_int(expected_revision + 1)
            con.execute(
                "INSERT INTO byot_owner_policy(owner_user_id,limit_cents,revision,updated_at)"
                " VALUES(?,?,?,?) ON CONFLICT(owner_user_id) DO UPDATE SET"
                " limit_cents=excluded.limit_cents,revision=excluded.revision,updated_at=excluded.updated_at",
                (owner, limit_cents, revision, datetime.now(UTC).isoformat()),
            )
            return OwnerPolicySnapshot(owner, limit_cents, revision)

    def begin_action(self, decision: OwnerActionDecision) -> ActionSnapshot:
        from substrate.byot_usage.ledger import OperationConflict

        if type(decision) is not OwnerActionDecision:
            raise ValueError("action decision is invalid")
        owner, action_id = decision.owner_user_id, decision.action_id
        with self._action_transaction() as con:
            existing = self._action_snapshot(con, owner, action_id)
            if existing is not None:
                if existing.decision != decision:
                    raise OperationConflict("action decision cannot be rebound")
                return existing
            self._insert_action(con, decision)
            return self._require_action(con, owner, action_id)

    def _insert_action(self, con: sqlite3.Connection, decision: OwnerActionDecision) -> None:
        self._admit_owner(con, decision.owner_user_id, decision.budget_cents)
        now = datetime.now(UTC).isoformat()
        con.execute(
            "INSERT INTO byot_action_journal(owner_user_id,action_id,action_kind,budget_cents,"
            " body_authority_digest,owner_decision_digest,epoch,state,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,0,'open',?,?)",
            (decision.owner_user_id, decision.action_id, decision.action_kind,
             decision.budget_cents, decision.body_authority_digest,
             decision.owner_decision_digest, now, now),
        )
        con.executemany(
            "INSERT INTO byot_action_routes(owner_user_id,action_id,ordinal,user_model_id,"
            " provider_id,model_id,route_digest) VALUES(?,?,?,?,?,?,?)",
            [(decision.owner_user_id, decision.action_id, i, route.user_model_id,
              route.provider_id, route.model_id, route.route_digest)
             for i, route in enumerate(decision.approved_routes)],
        )

    def admit_owned_wrestling(
        self, decision: OwnerActionDecision, *, investigation_id: str,
        document_id: str, source_reference: str, source_digest: str,
        request_event_id: str, delivered_event_id: str,
        request_payload_digest: str,
    ) -> OwnedWrestlingJob:
        """One money-DB transaction binds the decision, source and request outbox."""
        from substrate.byot_usage.ledger import OperationConflict

        if decision.action_kind != "long_document_wrestling":
            raise ValueError("wrong action kind")
        for value in (investigation_id, document_id, source_reference,
                      request_event_id, delivered_event_id):
            _identity(value)
        _digest(source_digest)
        _digest(request_payload_digest)
        owner, action_id = decision.owner_user_id, decision.action_id
        with self._action_transaction() as con:
            existing = _owned_job(con, owner, action_id)
            if existing is not None:
                if (self._require_action(con, owner, action_id).decision != decision
                    or (existing.investigation_id, existing.document_id,
                        existing.source_reference, existing.source_digest,
                        existing.request_event_id, existing.delivered_event_id,
                        existing.request_payload_digest) !=
                       (investigation_id, document_id, source_reference, source_digest,
                        request_event_id, delivered_event_id, request_payload_digest)):
                    raise OperationConflict("owned wrestling decision cannot be rebound")
                return existing
            if self._action_snapshot(con, owner, action_id) is not None:
                raise OperationConflict("action id already belongs to another workflow")
            self._insert_action(con, decision)
            con.execute(
                "INSERT INTO byot_owned_wrestling_job("
                "owner_user_id,action_id,investigation_id,document_id,source_reference,"
                "source_digest,request_event_id,delivered_event_id,request_payload_digest,"
                "state,canonical_input_reference,canonical_input_digest,result_reference,"
                "result_digest,execution_token,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,'queued',NULL,NULL,NULL,NULL,NULL,?)",
                (owner, action_id, investigation_id, document_id, source_reference,
                 source_digest, request_event_id, delivered_event_id,
                 request_payload_digest, datetime.now(UTC).isoformat()),
            )
            con.execute(
                "INSERT INTO byot_owned_wrestling_outbox VALUES(?,?, 'requested', ?, ?, NULL)",
                (owner, action_id, request_event_id, request_payload_digest),
            )
            return _owned_job(con, owner, action_id)  # type: ignore[return-value]

    def owned_wrestling_job(self, owner: str, action_id: str) -> OwnedWrestlingJob | None:
        _identity(owner)
        _identity(action_id)
        with self._action_transaction(write=False) as con:
            return _owned_job(con, owner, action_id)

    def owned_wrestling_for_request(self, request_event_id: str) -> OwnedWrestlingJob | None:
        _identity(request_event_id)
        with self._action_transaction(write=False) as con:
            row = con.execute(
                "SELECT owner_user_id,action_id FROM byot_owned_wrestling_job"
                " WHERE request_event_id=?", (request_event_id,),
            ).fetchone()
            return _owned_job(con, *row) if row else None

    def owned_wrestling_for_investigation(self, investigation_id: str) -> OwnedWrestlingJob | None:
        _identity(investigation_id)
        with self._action_transaction(write=False) as con:
            row = con.execute(
                "SELECT owner_user_id,action_id FROM byot_owned_wrestling_job"
                " WHERE investigation_id=?", (investigation_id,),
            ).fetchone()
            return _owned_job(con, *row) if row else None

    def claim_owned_wrestling_execution(
        self, owner: str, action_id: str, *, token: str, operation_id: str,
    ) -> OwnedWrestlingJob | None:
        """Elect one worker; settled output alone permits safe reconstruction."""
        _identity(token)
        _identity(operation_id)
        with self._action_transaction() as con:
            job = _owned_job(con, owner, action_id)
            if job is None:
                return None
            if job.state == "queued":
                pass
            elif job.state == "running":
                attempt = con.execute(
                    "SELECT state FROM byot_operation_journal"
                    " WHERE owner_user_id=? AND operation_id=? AND action_id=?",
                    (owner, operation_id, action_id),
                ).fetchone()
                if attempt != ("settled",):
                    return None
            else:
                return None
            con.execute(
                "UPDATE byot_owned_wrestling_job SET state='running',execution_token=?,"
                "updated_at=? WHERE owner_user_id=? AND action_id=?",
                (token, datetime.now(UTC).isoformat(), owner, action_id),
            )
            return _owned_job(con, owner, action_id)

    def bind_owned_wrestling_input(
        self, owner: str, action_id: str, *, reference: str, digest: str,
        execution_token: str | None = None,
    ) -> OwnedWrestlingJob:
        from substrate.byot_usage.ledger import OperationConflict

        _identity(reference)
        _digest(digest)
        with self._action_transaction() as con:
            job = _owned_job(con, owner, action_id)
            if (job is None or job.state != "running"
                or (job.execution_token is not None and job.execution_token != execution_token)):
                raise OperationConflict("owned wrestling is not running")
            if job.canonical_input_reference is not None:
                if (job.canonical_input_reference, job.canonical_input_digest) != (reference, digest):
                    raise OperationConflict("canonical input cannot be rebound")
                return job
            con.execute(
                "UPDATE byot_owned_wrestling_job SET canonical_input_reference=?,"
                "canonical_input_digest=?,updated_at=? WHERE owner_user_id=? AND action_id=?",
                (reference, digest, datetime.now(UTC).isoformat(), owner, action_id),
            )
            return _owned_job(con, owner, action_id)  # type: ignore[return-value]

    def transition_owned_wrestling(
        self, owner: str, action_id: str, *, expected: str, state: str,
        result_reference: str | None = None, result_digest: str | None = None,
        publication_payload_digest: str | None = None,
        execution_token: str | None = None,
    ) -> OwnedWrestlingJob:
        from substrate.byot_usage.ledger import OperationConflict

        if state not in {"running", "ready", "delivered", "unresolved", "refused"}:
            raise ValueError("invalid wrestling state")
        if (result_reference is None) != (result_digest is None):
            raise ValueError("result reference and digest must be paired")
        if result_reference is not None:
            _identity(result_reference)
            _digest(result_digest)
        if state == "ready":
            _digest(publication_payload_digest)
        with self._action_transaction() as con:
            job = _owned_job(con, owner, action_id)
            if (job is None or job.state != expected
                or (expected == "running" and job.execution_token is not None
                    and job.execution_token != execution_token)):
                raise OperationConflict("owned wrestling state changed")
            con.execute(
                "UPDATE byot_owned_wrestling_job SET state=?,result_reference=COALESCE(?,result_reference),"
                "result_digest=COALESCE(?,result_digest),updated_at=?"
                " WHERE owner_user_id=? AND action_id=?",
                (state, result_reference, result_digest, datetime.now(UTC).isoformat(),
                 owner, action_id),
            )
            if state == "ready":
                con.execute(
                    "INSERT INTO byot_owned_wrestling_outbox VALUES(?,?, 'delivered', ?, ?, NULL)",
                    (owner, action_id, job.delivered_event_id, publication_payload_digest),
                )
            return _owned_job(con, owner, action_id)  # type: ignore[return-value]

    def mark_owned_event_published(
        self, owner: str, action_id: str, kind: str, event_id: str,
        payload_digest: str,
    ) -> None:
        from substrate.byot_usage.ledger import OperationConflict

        if kind not in {"requested", "delivered"}:
            raise ValueError("invalid owned event kind")
        with self._action_transaction() as con:
            row = con.execute(
                "SELECT event_id,payload_digest FROM byot_owned_wrestling_outbox"
                " WHERE owner_user_id=? AND action_id=? AND event_kind=?",
                (owner, action_id, kind),
            ).fetchone()
            if row != (event_id, payload_digest):
                raise OperationConflict("owned event binding differs")
            con.execute(
                "UPDATE byot_owned_wrestling_outbox SET published_at=COALESCE(published_at,?)"
                " WHERE owner_user_id=? AND action_id=? AND event_kind=?",
                (datetime.now(UTC).isoformat(), owner, action_id, kind),
            )

    def publish_owned_wrestling_delivery(
        self, owner: str, action_id: str, event_id: str, payload_digest: str,
        *, already_present: bool, append: Callable[[], _Published],
    ) -> _Published | None:
        """Order the first durable append against cancellation in one money write."""
        from substrate.byot_usage.ledger import OperationConflict

        _identity(owner)
        _identity(action_id)
        _identity(event_id)
        _digest(payload_digest)
        with self._action_transaction() as con:
            job = _owned_job(con, owner, action_id)
            row = con.execute(
                "SELECT event_id,payload_digest,published_at"
                " FROM byot_owned_wrestling_outbox"
                " WHERE owner_user_id=? AND action_id=? AND event_kind='delivered'",
                (owner, action_id),
            ).fetchone()
            if (job is None or job.state not in {"ready", "delivered"}
                or row is None or row[:2] != (event_id, payload_digest)):
                raise OperationConflict("owned delivery binding differs")
            action = self._require_action(con, owner, action_id)
            if action.state != "open" and not already_present:
                return None
            published = append()
            con.execute(
                "UPDATE byot_owned_wrestling_outbox SET published_at=COALESCE(published_at,?)"
                " WHERE owner_user_id=? AND action_id=? AND event_kind='delivered'",
                (datetime.now(UTC).isoformat(), owner, action_id),
            )
            return published

    def _attempt(
        self, con: sqlite3.Connection, owner: str, attempt_id: str,
    ) -> ActionAttemptSnapshot | None:
        from substrate.byot_usage.ledger import OperationRow

        row = con.execute(
            "SELECT api_key_id,owner_user_id,operation_id,state,reserved_cents,actual_cents,"
            " authority_digest,evidence_sha256,provider_id,model_id,dispatch_event_id,result_text,"
            " created_at,updated_at,action_id,parent_operation_id,native_session_id,attempt_kind,"
            " route_digest,rate_limit_digest,action_epoch,request_digest,claim_nonce_digest,"
            " cost_micro_usd,result_reference FROM byot_operation_journal"
            " WHERE owner_user_id=? AND operation_id=? AND action_id IS NOT NULL",
            (owner, attempt_id),
        ).fetchone()
        if row is None:
            return None
        operation = OperationRow(*row[:15])
        proposal = AttemptProposal(row[2], row[0], row[8], row[9], row[18], row[6], row[19],
                                   row[4], row[20], row[15], row[16], row[17])
        return ActionAttemptSnapshot(operation, proposal, row[21], row[22], row[23], row[24])

    def _require_attempt(
        self, con: sqlite3.Connection, owner: str, attempt_id: str,
    ) -> ActionAttemptSnapshot:
        from substrate.byot_usage.ledger import OperationConflict

        attempt = self._attempt(con, owner, attempt_id)
        if attempt is None:
            raise OperationConflict("action attempt is unavailable")
        return attempt

    def action_attempt(self, owner: str, attempt_id: str) -> ActionAttemptSnapshot | None:
        _identity(owner)
        _identity(attempt_id)
        with self._action_transaction(write=False) as con:
            return self._attempt(con, owner, attempt_id)

    def allocate_action_attempt(
        self, owner: str, action_id: str, proposal: AttemptProposal,
    ) -> ActionAttemptSnapshot:
        from substrate.byot_usage.ledger import OperationConflict

        _identity(owner)
        _identity(action_id)
        if type(proposal) is not AttemptProposal:
            raise ValueError("attempt proposal is invalid")
        with self._action_transaction() as con:
            action = self._require_action(con, owner, action_id)
            existing = self._attempt(con, owner, proposal.operation_id)
            if existing is not None:
                if existing.proposal != proposal or existing.operation.action_id != action_id:
                    raise OperationConflict("attempt identity cannot be rebound")
                return existing
            if action.state != "open" or action.epoch != proposal.action_epoch:
                raise OperationConflict("action is not open at this epoch")
            self._admit_owner(con, owner, 0)
            route = ApprovedOwnerRoute(proposal.user_model_id, proposal.provider_id,
                                       proposal.model_id, proposal.route_digest)
            if route not in action.decision.approved_routes:
                raise OperationConflict("attempt route is not approved")
            if proposal.parent_operation_id is not None:
                parent = self._require_attempt(con, owner, proposal.parent_operation_id)
                if parent.operation.action_id != action_id or parent.operation.state == "cancelled":
                    raise OperationConflict("attempt parent is unavailable")
            if checked_sum([action.settled_cents, action.reserved_cents, proposal.reserved_cents]) > action.budget_cents:
                raise OperationConflict("attempt exceeds action budget")
            limit = con.execute(
                "SELECT limit_cents FROM byot_key_usage WHERE owner_user_id=? AND api_key_id=?",
                (owner, proposal.user_model_id),
            ).fetchone()
            exposure = checked_sum([record_exposure(con, owner, proposal.user_model_id),
                                    proposal.reserved_cents])
            if limit and limit[0] is not None and exposure > limit[0]:
                raise OperationConflict("attempt exceeds local record limit")
            now = datetime.now(UTC).isoformat()
            con.execute(
                "INSERT INTO byot_key_usage(api_key_id,owner_user_id,used_cents,updated_at)"
                " VALUES(?,?,0,?) ON CONFLICT(api_key_id,owner_user_id) DO NOTHING",
                (proposal.user_model_id, owner, now),
            )
            try:
                con.execute(
                    "INSERT INTO byot_operation_journal(api_key_id,owner_user_id,operation_id,state,"
                    " reserved_cents,authority_digest,provider_id,model_id,created_at,updated_at,"
                    " action_id,parent_operation_id,native_session_id,attempt_kind,route_digest,"
                    " rate_limit_digest,action_epoch) VALUES(?,?,?,'allocated',?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (proposal.user_model_id, owner, proposal.operation_id, proposal.reserved_cents,
                     proposal.authority_digest, proposal.provider_id, proposal.model_id, now, now,
                     action_id, proposal.parent_operation_id, proposal.native_session_id,
                     proposal.attempt_kind, proposal.route_digest, proposal.rate_limit_digest,
                     proposal.action_epoch),
                )
            except sqlite3.IntegrityError:
                raise OperationConflict("attempt identity is already in use") from None
            return self._require_attempt(con, owner, proposal.operation_id)

    def claim_action_attempt(
        self, owner: str, attempt_id: str, facts: FinalSendFacts,
    ) -> AttemptClaim:
        from substrate.byot_usage.ledger import OperationConflict

        _identity(owner)
        _identity(attempt_id)
        if type(facts) is not FinalSendFacts:
            raise ValueError("final send facts are invalid")
        with self._action_transaction() as con:
            attempt = self._require_attempt(con, owner, attempt_id)
            action = self._require_action(con, owner, attempt.operation.action_id or "")
            proposal = attempt.proposal
            if (facts.authority_digest != proposal.authority_digest
                or facts.route_digest != proposal.route_digest
                or facts.rate_limit_digest != proposal.rate_limit_digest
                or facts.body_authority_digest != action.decision.body_authority_digest
                or facts.action_epoch != proposal.action_epoch):
                raise OperationConflict("final request binding changed")
            if attempt.operation.state != "allocated":
                if (attempt.request_digest == facts.request_digest
                    and attempt.claim_nonce_digest == facts.claim_nonce_digest):
                    return AttemptClaim(False, attempt)
                raise OperationConflict("attempt is not claimable")
            if action.state != "open" or action.epoch != facts.action_epoch:
                raise OperationConflict("action claim was revoked")
            self._admit_owner(con, owner, 0)
            limit = con.execute(
                "SELECT limit_cents FROM byot_key_usage WHERE owner_user_id=? AND api_key_id=?",
                (owner, proposal.user_model_id),
            ).fetchone()
            exposure = record_exposure(con, owner, proposal.user_model_id)
            if limit and limit[0] is not None and exposure > limit[0]:
                raise OperationConflict("attempt exceeds current local record limit")
            try:
                con.execute(
                    "UPDATE byot_operation_journal SET state='sent',request_digest=?,"
                    " claim_nonce_digest=?,updated_at=? WHERE owner_user_id=? AND operation_id=?",
                    (facts.request_digest, facts.claim_nonce_digest, datetime.now(UTC).isoformat(),
                     owner, attempt_id),
                )
            except sqlite3.IntegrityError:
                raise OperationConflict("sender claim identity is already in use") from None
            return AttemptClaim(True, self._require_attempt(con, owner, attempt_id))

    def cancel_action_attempt(
        self, owner: str, attempt_id: str, *, expected_epoch: int,
    ) -> ActionAttemptSnapshot:
        from substrate.byot_usage.ledger import OperationConflict

        _identity(owner)
        _identity(attempt_id)
        checked_int(expected_epoch)
        with self._action_transaction() as con:
            attempt = self._require_attempt(con, owner, attempt_id)
            action = self._require_action(con, owner, attempt.operation.action_id or "")
            if (action.state != "open" or action.epoch != expected_epoch
                or attempt.proposal.action_epoch != expected_epoch
                or attempt.operation.state != "allocated"):
                raise OperationConflict("attempt is not provably unsent")
            con.execute(
                "UPDATE byot_operation_journal SET state='cancelled',updated_at=?"
                " WHERE owner_user_id=? AND operation_id=?",
                (datetime.now(UTC).isoformat(), owner, attempt_id),
            )
            return self._require_attempt(con, owner, attempt_id)

    def mark_action_attempt_unknown(self, owner: str, attempt_id: str) -> ActionAttemptSnapshot:
        from substrate.byot_usage.ledger import OperationConflict

        _identity(owner)
        _identity(attempt_id)
        with self._action_transaction() as con:
            attempt = self._require_attempt(con, owner, attempt_id)
            if attempt.operation.state == "unknown":
                return attempt
            if attempt.operation.state != "sent":
                raise OperationConflict("attempt cannot become unknown")
            con.execute(
                "UPDATE byot_operation_journal SET state='unknown',updated_at=?"
                " WHERE owner_user_id=? AND operation_id=?",
                (datetime.now(UTC).isoformat(), owner, attempt_id),
            )
            return self._require_attempt(con, owner, attempt_id)

    def _record_attempt_result(
        self, con: sqlite3.Connection, owner: str, attempt_id: str,
        facts: VerifiedAttemptFacts, *, allow_unknown: bool,
    ) -> ActionAttemptSnapshot:
        from substrate.byot_usage.ledger import OperationConflict, SettlementEvidenceError

        attempt = self._require_attempt(con, owner, attempt_id)
        if (facts.provider_id != attempt.proposal.provider_id
            or facts.model_id != attempt.proposal.model_id
            or facts.request_digest != attempt.request_digest):
            raise SettlementEvidenceError("attempt result binding differs")
        if attempt.operation.state in ("settlement_pending", "settled"):
            if (facts.actual_cents != attempt.operation.actual_cents
                or facts.cost_micro_usd != attempt.cost_micro_usd
                or facts.evidence_sha256 != attempt.operation.evidence_sha256
                or facts.provider_attempt_event_id != attempt.operation.dispatch_event_id
                or facts.result_reference != attempt.result_reference
                or facts.result_text != attempt.operation.result_text):
                raise SettlementEvidenceError("attempt result cannot be replaced")
            return attempt
        allowed = ("sent", "unknown") if allow_unknown else ("sent",)
        if attempt.operation.state not in allowed:
            raise OperationConflict("attempt result is not recordable")
        try:
            con.execute(
                "UPDATE byot_operation_journal SET state='settlement_pending',actual_cents=?,"
                " cost_micro_usd=?,evidence_sha256=?,dispatch_event_id=?,result_reference=?,result_text=?,"
                " updated_at=? WHERE owner_user_id=? AND operation_id=?",
                (facts.actual_cents, facts.cost_micro_usd, facts.evidence_sha256,
                 facts.provider_attempt_event_id, facts.result_reference, facts.result_text,
                 datetime.now(UTC).isoformat(), owner, attempt_id),
            )
        except sqlite3.IntegrityError:
            raise SettlementEvidenceError("provider attempt evidence is already recorded") from None
        if facts.actual_cents > attempt.proposal.reserved_cents:
            action_id = attempt.operation.action_id or ""
            action = self._require_action(con, owner, action_id)
            con.execute(
                "UPDATE byot_action_journal SET quarantined=1,epoch=?,"
                " state=CASE WHEN state='open' THEN 'quarantined' ELSE state END,updated_at=?"
                " WHERE owner_user_id=? AND action_id=?",
                (checked_int(action.epoch + 1), datetime.now(UTC).isoformat(), owner, action_id),
            )
            con.execute(
                "UPDATE byot_operation_journal SET state='cancelled',updated_at=?"
                " WHERE owner_user_id=? AND action_id=? AND state='allocated'",
                (datetime.now(UTC).isoformat(), owner, action_id),
            )
        return self._require_attempt(con, owner, attempt_id)

    def record_action_attempt_result(
        self, owner: str, attempt_id: str, facts: VerifiedAttemptFacts,
    ) -> ActionAttemptSnapshot:
        _identity(owner)
        _identity(attempt_id)
        if type(facts) is not VerifiedAttemptFacts:
            raise ValueError("attempt result is invalid")
        with self._action_transaction() as con:
            return self._record_attempt_result(con, owner, attempt_id, facts, allow_unknown=False)

    def _settle_attempt(
        self, con: sqlite3.Connection, owner: str, attempt_id: str,
    ) -> ActionAttemptSnapshot:
        from substrate.byot_usage.ledger import OperationConflict, SettlementEvidenceError

        attempt = self._require_attempt(con, owner, attempt_id)
        operation = attempt.operation
        if operation.state == "settled":
            return attempt
        if operation.state != "settlement_pending":
            raise OperationConflict("attempt is not settleable")
        if (operation.actual_cents is None or attempt.cost_micro_usd is None
            or operation.evidence_sha256 is None or operation.dispatch_event_id is None
            or attempt.request_digest is None
            or operation.actual_cents != (attempt.cost_micro_usd + 9999) // 10000):
            raise SettlementEvidenceError("attempt lacks persisted usage evidence")
        checked_int(operation.actual_cents)
        used = con.execute(
            "SELECT used_cents FROM byot_key_usage WHERE owner_user_id=? AND api_key_id=?",
            (owner, operation.api_key_id),
        ).fetchone()
        if used is None:
            raise SettlementEvidenceError("attempt usage record is unavailable")
        new_used = checked_sum([used[0], operation.actual_cents])
        owner_used = self._owner_usage(con, owner).used_cents
        checked_sum([owner_used, operation.actual_cents])
        now = datetime.now(UTC).isoformat()
        con.execute(
            "UPDATE byot_key_usage SET used_cents=?,last_settled_at=?,updated_at=?"
            " WHERE owner_user_id=? AND api_key_id=?",
            (new_used, now, now, owner, operation.api_key_id),
        )
        con.execute(
            "UPDATE byot_operation_journal SET state='settled',updated_at=?"
            " WHERE owner_user_id=? AND operation_id=?", (now, owner, attempt_id),
        )
        cursor = con.execute(
            "INSERT INTO byot_action_outbox(owner_user_id,action_id,operation_id,occurred_at,digest)"
            " VALUES(?,?,?,?,'')", (owner, operation.action_id, attempt_id, now),
        )
        sequence = cursor.lastrowid
        if sequence is None:
            raise RuntimeError("settlement event was not persisted")
        event = self._event(con, sequence, validate=False)
        digest = hashlib.sha256(event.canonical_payload().encode()).hexdigest()
        con.execute("UPDATE byot_action_outbox SET digest=? WHERE sequence=?", (digest, sequence))
        self._finish_closing(con, owner, operation.action_id or "")
        return self._require_attempt(con, owner, attempt_id)

    def settle_action_attempt(self, owner: str, attempt_id: str) -> ActionAttemptSnapshot:
        _identity(owner)
        _identity(attempt_id)
        with self._action_transaction() as con:
            return self._settle_attempt(con, owner, attempt_id)

    def reconcile_action_attempt_usage(
        self, owner: str, attempt_id: str, facts: VerifiedAttemptFacts,
    ) -> ActionAttemptSnapshot:
        _identity(owner)
        _identity(attempt_id)
        if type(facts) is not VerifiedAttemptFacts:
            raise ValueError("attempt result is invalid")
        with self._action_transaction() as con:
            self._record_attempt_result(con, owner, attempt_id, facts, allow_unknown=True)
            return self._settle_attempt(con, owner, attempt_id)

    def _finish_closing(self, con: sqlite3.Connection, owner: str, action_id: str) -> None:
        if not con.execute(
            "SELECT 1 FROM byot_operation_journal WHERE owner_user_id=? AND action_id=?"
            f" AND state IN {ACTIVE_STATES} LIMIT 1", (owner, action_id),
        ).fetchone():
            con.execute(
                "UPDATE byot_action_journal SET state='closed',updated_at=?"
                " WHERE owner_user_id=? AND action_id=? AND state='closing'",
                (datetime.now(UTC).isoformat(), owner, action_id),
            )

    def close_action(
        self, owner: str, action_id: str, *, expected_epoch: int,
    ) -> ActionSnapshot:
        from substrate.byot_usage.ledger import OperationConflict

        _identity(owner)
        _identity(action_id)
        checked_int(expected_epoch)
        with self._action_transaction() as con:
            action = self._require_action(con, owner, action_id)
            if action.state in ("closing", "closed"):
                if action.epoch not in (expected_epoch, expected_epoch + 1):
                    raise OperationConflict("action epoch changed")
                return action
            if action.epoch != expected_epoch:
                raise OperationConflict("action epoch changed")
            now = datetime.now(UTC).isoformat()
            con.execute(
                "UPDATE byot_action_journal SET state='closing',epoch=?,updated_at=?"
                " WHERE owner_user_id=? AND action_id=?",
                (checked_int(expected_epoch + 1), now, owner, action_id),
            )
            con.execute(
                "UPDATE byot_operation_journal SET state='cancelled',updated_at=?"
                " WHERE owner_user_id=? AND action_id=? AND state='allocated'", (now, owner, action_id),
            )
            self._finish_closing(con, owner, action_id)
            return self._require_action(con, owner, action_id)

    def _event(
        self, con: sqlite3.Connection, sequence: int, *, validate: bool = True,
    ) -> OwnerAttemptEvent:
        from substrate.byot_usage.ledger import OperationConflict

        row = con.execute(
            "SELECT m.value,o.sequence,o.owner_user_id,o.action_id,o.operation_id,j.api_key_id,"
            " j.provider_id,j.model_id,j.authority_digest,j.request_digest,j.evidence_sha256,"
            " j.dispatch_event_id,j.cost_micro_usd,j.actual_cents,o.occurred_at,o.digest"
            " FROM byot_action_outbox o JOIN byot_operation_journal j"
            " ON j.owner_user_id=o.owner_user_id AND j.operation_id=o.operation_id"
            " JOIN byot_usage_meta m ON m.key='journal_id' WHERE o.sequence=?", (sequence,),
        ).fetchone()
        if row is None:
            raise OperationConflict("settlement event is unavailable")
        if validate:
            _digest(row[-1])
        return OwnerAttemptEvent(*row)

    def pending_projection_events(
        self, *, after_sequence: int = 0, limit: int = 100,
    ) -> tuple[OwnerAttemptEvent, ...]:
        checked_int(after_sequence)
        checked_int(limit, minimum=1)
        if limit > 1000:
            raise ValueError("outbox batch is too large")
        with self._action_transaction(write=False) as con:
            sequences = con.execute(
                "SELECT sequence FROM byot_action_outbox WHERE acknowledged_at IS NULL"
                " AND sequence>? ORDER BY sequence LIMIT ?", (after_sequence, limit),
            ).fetchall()
            return tuple(self._event(con, row[0]) for row in sequences)

    def acknowledge_projection(self, sequence: int, digest: str) -> None:
        from substrate.byot_usage.ledger import SettlementEvidenceError

        checked_int(sequence, minimum=1)
        _digest(digest)
        with self._action_transaction() as con:
            event = self._event(con, sequence)
            if event.digest != digest:
                raise SettlementEvidenceError("projection acknowledgement differs")
            con.execute(
                "UPDATE byot_action_outbox SET acknowledged_at=? WHERE sequence=?"
                " AND acknowledged_at IS NULL", (datetime.now(UTC).isoformat(), sequence),
            )
