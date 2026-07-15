"""Owner-private research-plan authority and ordered manual tree edits."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import stat
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .research_intent import ResearchIntent

_V1_COLUMNS = (
    "plan_id", "owner_identity_digest", "source_intent_id", "source_intent_digest",
    "source_evidence_digest", "idempotency_key", "request_digest", "plan_version",
    "plan_json", "created_at", "updated_at",
)
_PLAN_COLUMNS = _V1_COLUMNS + ("plan_integrity_digest",)
_RECEIPT_COLUMNS = (
    "owner_identity_digest", "plan_id", "idempotency_key", "request_digest",
    "base_plan_version", "result_plan_version", "before_plan_integrity_digest",
    "after_plan_integrity_digest", "response_json", "created_at",
)
_PREPARED_COLUMNS = (
    "investigation_id", "owner_identity_digest", "source_plan_id",
    "source_plan_version", "source_plan_integrity_digest", "source_intent_id",
    "source_intent_digest", "source_evidence_digest", "idempotency_key",
    "request_digest", "prepared_json", "prepared_integrity_digest", "created_at",
)
_AUTHORIZATION_COLUMNS = (
    "authorization_id", "owner_identity_digest", "investigation_id", "idempotency_key",
    "request_digest", "prepared_integrity_digest", "source_plan_id", "source_plan_version",
    "source_plan_integrity_digest", "source_intent_id", "source_intent_digest",
    "source_evidence_digest", "total_node_count", "leaf_question_count", "route_policy",
    "resolved_tier", "provider", "model", "dispatch_config_digest", "pricing_source",
    "pricing_digest", "workload_digest", "quoted_ceiling_cents", "quote_id",
    "quote_issued_at", "quote_expires_at", "quote_digest", "approved_ceiling_cents",
    "ttl_seconds", "issued_at", "expires_at", "authorization_json",
    "authorization_integrity_digest",
)
_LAUNCH_COLUMNS = (
    "launch_reservation_id", "owner_identity_digest", "authorization_id",
    "investigation_id", "idempotency_key", "request_digest",
    "prepared_integrity_digest", "authorization_integrity_digest", "source_plan_id",
    "source_plan_version", "source_plan_integrity_digest", "source_intent_id",
    "source_intent_digest", "source_evidence_digest", "total_node_count",
    "leaf_question_count", "route_policy", "resolved_tier", "provider", "model",
    "dispatch_config_digest", "pricing_source", "pricing_digest", "workload_digest",
    "quoted_ceiling_cents", "approved_ceiling_cents", "launch_manifest_digest",
    "spend_run_id", "session_id", "reserved_cents", "reserved_at", "state",
    "execution_started", "background_work_authorized", "event_authority_digest",
    "graph_authority_digest", "provider_authority_digest", "task_authority_digest",
    "reservation_json", "reservation_integrity_digest",
)
_V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS multimedia_research_plans (
  plan_id TEXT PRIMARY KEY, owner_identity_digest TEXT NOT NULL,
  source_intent_id TEXT NOT NULL, source_intent_digest TEXT NOT NULL,
  source_evidence_digest TEXT NOT NULL, idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL, plan_version INTEGER NOT NULL,
  plan_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(owner_identity_digest, idempotency_key),
  UNIQUE(owner_identity_digest, source_intent_id)
)
"""
_V2_PLAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS multimedia_research_plans (
  plan_id TEXT PRIMARY KEY, owner_identity_digest TEXT NOT NULL,
  source_intent_id TEXT NOT NULL, source_intent_digest TEXT NOT NULL,
  source_evidence_digest TEXT NOT NULL, idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL, plan_version INTEGER NOT NULL CHECK(plan_version >= 1),
  plan_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  plan_integrity_digest TEXT NOT NULL CHECK(length(plan_integrity_digest) = 64),
  UNIQUE(owner_identity_digest, idempotency_key),
  UNIQUE(owner_identity_digest, source_intent_id)
)
"""
_V2_RECEIPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS multimedia_research_plan_mutations (
  owner_identity_digest TEXT NOT NULL, plan_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL,
  base_plan_version INTEGER NOT NULL CHECK(base_plan_version >= 1),
  result_plan_version INTEGER NOT NULL CHECK(result_plan_version = base_plan_version + 1),
  before_plan_integrity_digest TEXT NOT NULL CHECK(length(before_plan_integrity_digest) = 64),
  after_plan_integrity_digest TEXT NOT NULL CHECK(length(after_plan_integrity_digest) = 64),
  response_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(owner_identity_digest, plan_id, idempotency_key),
  UNIQUE(owner_identity_digest, plan_id, result_plan_version),
  FOREIGN KEY(plan_id) REFERENCES multimedia_research_plans(plan_id)
)
"""
_V3_PREPARED_SCHEMA = """
CREATE TABLE IF NOT EXISTS multimedia_prepared_investigations (
  investigation_id TEXT PRIMARY KEY, owner_identity_digest TEXT NOT NULL,
  source_plan_id TEXT NOT NULL, source_plan_version INTEGER NOT NULL CHECK(source_plan_version >= 1),
  source_plan_integrity_digest TEXT NOT NULL CHECK(length(source_plan_integrity_digest) = 64),
  source_intent_id TEXT NOT NULL,
  source_intent_digest TEXT NOT NULL CHECK(length(source_intent_digest) = 64),
  source_evidence_digest TEXT NOT NULL CHECK(length(source_evidence_digest) = 64),
  idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL CHECK(length(request_digest) = 64), prepared_json TEXT NOT NULL,
  prepared_integrity_digest TEXT NOT NULL CHECK(length(prepared_integrity_digest) = 64),
  created_at TEXT NOT NULL,
  UNIQUE(owner_identity_digest, idempotency_key),
  UNIQUE(owner_identity_digest, source_plan_id),
  FOREIGN KEY(source_plan_id) REFERENCES multimedia_research_plans(plan_id)
)
"""
_V4_AUTHORIZATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS multimedia_investigation_activation_authorizations (
  authorization_id TEXT PRIMARY KEY, owner_identity_digest TEXT NOT NULL,
  investigation_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL CHECK(length(request_digest) = 64),
  prepared_integrity_digest TEXT NOT NULL CHECK(length(prepared_integrity_digest) = 64),
  source_plan_id TEXT NOT NULL, source_plan_version INTEGER NOT NULL CHECK(source_plan_version >= 1),
  source_plan_integrity_digest TEXT NOT NULL CHECK(length(source_plan_integrity_digest) = 64),
  source_intent_id TEXT NOT NULL,
  source_intent_digest TEXT NOT NULL CHECK(length(source_intent_digest) = 64),
  source_evidence_digest TEXT NOT NULL CHECK(length(source_evidence_digest) = 64),
  total_node_count INTEGER NOT NULL CHECK(total_node_count >= 1),
  leaf_question_count INTEGER NOT NULL CHECK(leaf_question_count >= 1),
  route_policy TEXT NOT NULL, resolved_tier TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  dispatch_config_digest TEXT NOT NULL CHECK(length(dispatch_config_digest) = 64),
  pricing_source TEXT NOT NULL, pricing_digest TEXT NOT NULL CHECK(length(pricing_digest) = 64),
  workload_digest TEXT NOT NULL CHECK(length(workload_digest) = 64),
  quoted_ceiling_cents INTEGER NOT NULL CHECK(quoted_ceiling_cents > 0 AND quoted_ceiling_cents <= 9223372036854775807), quote_id TEXT NOT NULL,
  quote_issued_at TEXT NOT NULL, quote_expires_at TEXT NOT NULL,
  quote_digest TEXT NOT NULL CHECK(length(quote_digest) = 64),
  approved_ceiling_cents INTEGER NOT NULL CHECK(approved_ceiling_cents > 0 AND approved_ceiling_cents <= 9223372036854775807),
  ttl_seconds INTEGER NOT NULL CHECK(ttl_seconds >= 60 AND ttl_seconds <= 86400),
  issued_at TEXT NOT NULL, expires_at TEXT NOT NULL, authorization_json TEXT NOT NULL,
  authorization_integrity_digest TEXT NOT NULL CHECK(length(authorization_integrity_digest) = 64),
  UNIQUE(owner_identity_digest, investigation_id, idempotency_key),
  UNIQUE(owner_identity_digest, investigation_id),
  FOREIGN KEY(investigation_id) REFERENCES multimedia_prepared_investigations(investigation_id)
)
"""
_V5_LAUNCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS multimedia_investigation_launch_reservations (
  launch_reservation_id TEXT PRIMARY KEY, owner_identity_digest TEXT NOT NULL,
  authorization_id TEXT NOT NULL, investigation_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL CHECK(length(request_digest) = 64),
  prepared_integrity_digest TEXT NOT NULL CHECK(length(prepared_integrity_digest) = 64),
  authorization_integrity_digest TEXT NOT NULL CHECK(length(authorization_integrity_digest) = 64),
  source_plan_id TEXT NOT NULL, source_plan_version INTEGER NOT NULL CHECK(source_plan_version >= 1),
  source_plan_integrity_digest TEXT NOT NULL CHECK(length(source_plan_integrity_digest) = 64),
  source_intent_id TEXT NOT NULL,
  source_intent_digest TEXT NOT NULL CHECK(length(source_intent_digest) = 64),
  source_evidence_digest TEXT NOT NULL CHECK(length(source_evidence_digest) = 64),
  total_node_count INTEGER NOT NULL CHECK(total_node_count >= 1),
  leaf_question_count INTEGER NOT NULL CHECK(leaf_question_count >= 1),
  route_policy TEXT NOT NULL, resolved_tier TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  dispatch_config_digest TEXT NOT NULL CHECK(length(dispatch_config_digest) = 64),
  pricing_source TEXT NOT NULL, pricing_digest TEXT NOT NULL CHECK(length(pricing_digest) = 64),
  workload_digest TEXT NOT NULL CHECK(length(workload_digest) = 64),
  quoted_ceiling_cents INTEGER NOT NULL CHECK(quoted_ceiling_cents > 0 AND quoted_ceiling_cents <= 9223372036854775807),
  approved_ceiling_cents INTEGER NOT NULL CHECK(approved_ceiling_cents > 0 AND approved_ceiling_cents <= 9223372036854775807),
  launch_manifest_digest TEXT NOT NULL CHECK(length(launch_manifest_digest) = 64),
  spend_run_id TEXT NOT NULL UNIQUE, session_id TEXT NOT NULL UNIQUE,
  reserved_cents INTEGER NOT NULL CHECK(reserved_cents > 0 AND reserved_cents <= 9223372036854775807),
  reserved_at TEXT NOT NULL, state TEXT NOT NULL CHECK(state = 'launch_reserved'),
  execution_started INTEGER NOT NULL CHECK(execution_started = 0),
  background_work_authorized INTEGER NOT NULL CHECK(background_work_authorized = 0),
  event_authority_digest TEXT, graph_authority_digest TEXT, provider_authority_digest TEXT,
  task_authority_digest TEXT, reservation_json TEXT NOT NULL,
  reservation_integrity_digest TEXT NOT NULL CHECK(length(reservation_integrity_digest) = 64),
  UNIQUE(owner_identity_digest, authorization_id, idempotency_key),
  UNIQUE(owner_identity_digest, authorization_id),
  UNIQUE(owner_identity_digest, investigation_id),
  FOREIGN KEY(authorization_id) REFERENCES multimedia_investigation_activation_authorizations(authorization_id),
  FOREIGN KEY(investigation_id) REFERENCES multimedia_prepared_investigations(investigation_id)
)
"""

_MAX_RECORD_BYTES = 128 * 1024
_MAX_NODES = 256
_MAX_DEPTH = 8
_MAX_CHILDREN = 64
_MAX_OPERATIONS = 64
_MAX_CENTS = 9_223_372_036_854_775_807


class ResearchPlanError(RuntimeError):
    """The plan is unavailable or conflicts with immutable authority."""


class ResearchPlanUnavailableError(ResearchPlanError):
    """No owner-visible plan exists for the requested identity."""


class ResearchPlanStorageError(ResearchPlanError):
    """The private plan authority cannot be read or written safely."""


class ResearchPlanValidationError(ResearchPlanError):
    """A requested edit is invalid and made no changes."""


class ResearchPlanTooLargeError(ResearchPlanValidationError):
    """A canonical request or result exceeds the private authority bound."""


@dataclass(frozen=True)
class PreparedInvestigation:
    investigation_id: str
    source_plan_id: str
    source_plan_version: int
    source_plan_integrity_digest: str
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    tree: dict[str, object]
    total_node_count: int
    leaf_question_count: int
    request_digest: str
    state: str
    created_at: str
    execution_started: bool = False
    background_work_authorized: bool = False
    event_authority_digest: None = None
    graph_authority_digest: None = None
    provider_authority_digest: None = None
    spend_authority_digest: None = None


@dataclass(frozen=True)
class InvestigationActivationQuote:
    schema_version: int
    route_policy: str
    resolved_tier: str
    provider: str
    model: str
    dispatch_config_digest: str
    pricing_source: str
    pricing_digest: str
    workload_digest: str
    quoted_ceiling_cents: int
    quote_id: str
    issued_at: str
    expires_at: str


@dataclass(frozen=True)
class InvestigationActivationAuthorization:
    authorization_id: str
    investigation_id: str
    prepared_integrity_digest: str
    source_plan_id: str
    source_plan_version: int
    source_plan_integrity_digest: str
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    total_node_count: int
    leaf_question_count: int
    route_policy: str
    resolved_tier: str
    provider: str
    model: str
    dispatch_config_digest: str
    pricing_source: str
    pricing_digest: str
    workload_digest: str
    quoted_ceiling_cents: int
    quote_id: str
    quote_issued_at: str
    quote_expires_at: str
    quote_digest: str
    approved_ceiling_cents: int
    ttl_seconds: int
    request_digest: str
    issued_at: str
    expires_at: str
    state: str = "authorized"
    execution_started: bool = False
    event_authority_digest: None = None
    graph_authority_digest: None = None
    provider_authority_digest: None = None
    spend_reservation_digest: None = None
    consumed_at: None = None
    background_work_authorized: bool = False

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= _parse_timestamp(self.expires_at)


@dataclass(frozen=True)
class InvestigationLaunchReservation:
    launch_reservation_id: str
    authorization_id: str
    investigation_id: str
    prepared_integrity_digest: str
    authorization_integrity_digest: str
    source_plan_id: str
    source_plan_version: int
    source_plan_integrity_digest: str
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    total_node_count: int
    leaf_question_count: int
    route_policy: str
    resolved_tier: str
    provider: str
    model: str
    dispatch_config_digest: str
    pricing_source: str
    pricing_digest: str
    workload_digest: str
    quoted_ceiling_cents: int
    approved_ceiling_cents: int
    launch_manifest_digest: str
    request_digest: str
    spend_run_id: str
    session_id: str
    reserved_cents: int
    reserved_at: str
    state: str = "launch_reserved"
    execution_started: bool = False
    background_work_authorized: bool = False
    event_authority_digest: None = None
    graph_authority_digest: None = None
    provider_authority_digest: None = None
    task_authority_digest: None = None


@dataclass(frozen=True)
class ResearchPlan:
    plan_id: str
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    request_digest: str
    state: str
    plan_version: int
    tree: dict[str, object]
    created_at: str
    updated_at: str
    approved_at: str | None = None
    approved_by_owner_digest: str | None = None
    research_launched: bool = False
    provider_launch_authorized: bool = False
    spend_authority_digest: None = None


class ResearchPlanLedger:
    def __init__(self, store_root: str | os.PathLike[str]) -> None:
        root = Path(store_root)
        if not root.is_dir() or root.is_symlink():
            raise ValueError("multimedia store root is invalid")
        metadata = root.stat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
            raise ValueError("multimedia store root is not privately controlled")
        self.path = root / "research-plans.sqlite3"

    def handoff(
        self, *, owner_identity_digest: str, idempotency_key: str, intent: ResearchIntent
    ) -> tuple[ResearchPlan, bool]:
        _validate_owner(owner_identity_digest)
        _validate_key(idempotency_key)
        seed = intent.plan_seed
        request_digest = _digest({
            "source_intent_id": intent.intent_id,
            "source_intent_digest": seed["intent_digest"],
            "source_evidence_digest": intent.evidence_digest,
            "question": intent.question,
        })
        now = _now()
        plan = ResearchPlan(
            plan_id="mrp_" + secrets.token_hex(24), source_intent_id=intent.intent_id,
            source_intent_digest=seed["intent_digest"],
            source_evidence_digest=intent.evidence_digest, request_digest=request_digest,
            state="draft", plan_version=1,
            tree={"root": {
                "node_id": _new_node_id(), "kind": "research_question",
                "question": intent.question, "source_intent_id": intent.intent_id,
                "source_intent_digest": seed["intent_digest"],
                "source_evidence_digest": intent.evidence_digest, "children": [],
            }}, created_at=now, updated_at=now,
        )
        raw = _encode(plan, owner_identity_digest, idempotency_key)
        _check_size(raw, "research plan is too large")
        integrity = _plan_digest(plan)
        connection = self._connect()
        try:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT " + ",".join(_PLAN_COLUMNS) + " FROM multimedia_research_plans "
                "WHERE owner_identity_digest=? AND (idempotency_key=? OR source_intent_id=?)",
                (owner_identity_digest, idempotency_key, intent.intent_id),
            ).fetchone()
            if row is not None:
                existing = self._decode_row(row, owner_identity_digest)
                if row[5] != idempotency_key or row[6] != request_digest:
                    raise ResearchPlanError("research plan idempotency conflict")
                connection.commit()
                return existing, False
            connection.execute(
                "INSERT INTO multimedia_research_plans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (plan.plan_id, owner_identity_digest, plan.source_intent_id,
                 plan.source_intent_digest, plan.source_evidence_digest, idempotency_key,
                 plan.request_digest, plan.plan_version, raw, plan.created_at, plan.updated_at,
                 integrity),
            )
            connection.commit()
            return plan, True
        except sqlite3.Error as exc:
            connection.rollback()
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, *, owner_identity_digest: str, plan_id: str) -> ResearchPlan:
        _validate_owner(owner_identity_digest)
        _validate_plan_id(plan_id)
        connection = self._connect_existing()
        try:
            self._initialize(connection)
            row = self._select_plan(connection, owner_identity_digest, plan_id)
            if row is None:
                raise ResearchPlanUnavailableError("research plan is unavailable")
            return self._decode_row(row, owner_identity_digest)
        except sqlite3.Error as exc:
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        finally:
            connection.close()

    def approve(
        self, *, owner_identity_digest: str, plan_id: str, expected_plan_version: int
    ) -> ResearchPlan:
        _validate_owner(owner_identity_digest)
        _validate_plan_id(plan_id)
        _validate_version(expected_plan_version)
        connection = self._connect_existing()
        try:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = self._select_plan(connection, owner_identity_digest, plan_id)
            if row is None:
                raise ResearchPlanUnavailableError("research plan is unavailable")
            plan = self._decode_row(row, owner_identity_digest)
            if plan.plan_version != expected_plan_version:
                raise ResearchPlanError("research plan version conflict")
            if plan.state == "approved":
                connection.commit()
                return plan
            now = _now()
            approved = replace(plan, state="approved", approved_at=now,
                               approved_by_owner_digest=owner_identity_digest, updated_at=now)
            raw = _encode(approved, owner_identity_digest, str(row[5]))
            integrity = _plan_digest(approved)
            changed = connection.execute(
                "UPDATE multimedia_research_plans SET plan_json=?,updated_at=?,"
                "plan_integrity_digest=? WHERE owner_identity_digest=? AND plan_id=? "
                "AND plan_version=? AND plan_integrity_digest=?",
                (raw, now, integrity, owner_identity_digest, plan_id, expected_plan_version, row[11]),
            ).rowcount
            if changed != 1:
                raise ResearchPlanError("research plan version conflict")
            connection.commit()
            return approved
        except sqlite3.Error as exc:
            connection.rollback()
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def edit(
        self, *, owner_identity_digest: str, plan_id: str, idempotency_key: str,
        expected_plan_version: int, operations: list[dict[str, object]],
    ) -> ResearchPlan:
        _validate_owner(owner_identity_digest)
        _validate_plan_id(plan_id)
        _validate_key(idempotency_key)
        _validate_version(expected_plan_version)
        normalized = _validate_operations(operations)
        request = {"expected_plan_version": expected_plan_version, "operations": normalized}
        request_raw = _canonical(request)
        _check_size(request_raw, "research plan edit request is too large")
        request_digest = _digest(request)
        connection = self._connect_existing()
        try:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                "SELECT " + ",".join(_RECEIPT_COLUMNS) + " FROM multimedia_research_plan_mutations "
                "WHERE owner_identity_digest=? AND plan_id=? AND idempotency_key=?",
                (owner_identity_digest, plan_id, idempotency_key),
            ).fetchone()
            if receipt is not None:
                replay = self._decode_receipt(receipt, owner_identity_digest)
                if receipt[3] != request_digest:
                    raise ResearchPlanError("research plan edit idempotency conflict")
                connection.commit()
                return replay
            row = self._select_plan(connection, owner_identity_digest, plan_id)
            if row is None:
                raise ResearchPlanUnavailableError("research plan is unavailable")
            plan = self._decode_row(row, owner_identity_digest)
            if plan.plan_version != expected_plan_version:
                raise ResearchPlanError("research plan version conflict")
            tree = deepcopy(plan.tree)
            for operation in normalized:
                _apply_operation(tree, operation)
                _validate_tree(tree, plan)
            now = _now()
            edited = replace(plan, tree=tree, plan_version=plan.plan_version + 1,
                             state="draft", approved_at=None,
                             approved_by_owner_digest=None, updated_at=now)
            _assert_plan_integrity(edited, owner_identity_digest)
            raw = _encode(edited, owner_identity_digest, str(row[5]))
            response_raw = _canonical(asdict(edited))
            _check_size(raw, "research plan edit result is too large")
            _check_size(response_raw, "research plan edit result is too large")
            before_digest, after_digest = str(row[11]), _plan_digest(edited)
            changed = connection.execute(
                "UPDATE multimedia_research_plans SET plan_version=?,plan_json=?,updated_at=?,"
                "plan_integrity_digest=? WHERE owner_identity_digest=? AND plan_id=? "
                "AND plan_version=? AND plan_integrity_digest=?",
                (edited.plan_version, raw, now, after_digest, owner_identity_digest, plan_id,
                 expected_plan_version, before_digest),
            ).rowcount
            if changed != 1:
                raise ResearchPlanError("research plan version conflict")
            connection.execute(
                "INSERT INTO multimedia_research_plan_mutations VALUES (?,?,?,?,?,?,?,?,?,?)",
                (owner_identity_digest, plan_id, idempotency_key, request_digest,
                 expected_plan_version, edited.plan_version, before_digest, after_digest,
                 response_raw, now),
            )
            connection.commit()
            return edited
        except sqlite3.Error as exc:
            connection.rollback()
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def prepare_investigation(
        self, *, owner_identity_digest: str, plan_id: str, idempotency_key: str,
        expected_plan_version: int,
    ) -> tuple[PreparedInvestigation, bool]:
        _validate_owner(owner_identity_digest)
        _validate_plan_id(plan_id)
        _validate_key(idempotency_key)
        _validate_version(expected_plan_version)
        request = {"expected_plan_version": expected_plan_version, "source_plan_id": plan_id}
        request_raw = _canonical(request)
        _check_size(request_raw, "prepared investigation request is too large")
        request_digest = _digest(request)
        connection = self._connect_existing()
        try:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            replay_row = connection.execute(
                "SELECT " + ",".join(_PREPARED_COLUMNS)
                + " FROM multimedia_prepared_investigations "
                "WHERE owner_identity_digest=? AND idempotency_key=?",
                (owner_identity_digest, idempotency_key),
            ).fetchone()
            if replay_row is not None:
                replay = self._decode_prepared_row(replay_row, owner_identity_digest)
                if replay_row[9] != request_digest:
                    raise ResearchPlanError("prepared investigation idempotency conflict")
                connection.commit()
                return replay, False
            existing = connection.execute(
                "SELECT " + ",".join(_PREPARED_COLUMNS)
                + " FROM multimedia_prepared_investigations "
                "WHERE owner_identity_digest=? AND source_plan_id=?",
                (owner_identity_digest, plan_id),
            ).fetchone()
            if existing is not None:
                self._decode_prepared_row(existing, owner_identity_digest)
                raise ResearchPlanError("research plan is already prepared")
            plan_row = self._select_plan(connection, owner_identity_digest, plan_id)
            if plan_row is None:
                raise ResearchPlanUnavailableError("research plan is unavailable")
            plan = self._decode_row(plan_row, owner_identity_digest)
            if plan.plan_version != expected_plan_version:
                raise ResearchPlanError("research plan version conflict")
            if (plan.state != "approved" or plan.approved_by_owner_digest != owner_identity_digest
                    or not _timestamp(plan.approved_at) or plan.research_launched is not False
                    or plan.provider_launch_authorized is not False
                    or plan.spend_authority_digest is not None):
                raise ResearchPlanError("research plan is not approved")
            tree = deepcopy(plan.tree)
            _validate_tree(tree, plan)
            total_nodes, leaf_questions = _tree_counts(tree)
            prepared = PreparedInvestigation(
                investigation_id="mpi_" + secrets.token_hex(24), source_plan_id=plan.plan_id,
                source_plan_version=plan.plan_version,
                source_plan_integrity_digest=str(plan_row[11]),
                source_intent_id=plan.source_intent_id,
                source_intent_digest=plan.source_intent_digest,
                source_evidence_digest=plan.source_evidence_digest, tree=tree,
                total_node_count=total_nodes, leaf_question_count=leaf_questions,
                request_digest=request_digest, state="prepared", created_at=_now(),
            )
            _assert_prepared_integrity(prepared)
            raw = _encode_prepared(prepared, owner_identity_digest, idempotency_key)
            response_raw = _canonical(asdict(prepared))
            _check_size(raw, "prepared investigation is too large")
            _check_size(response_raw, "prepared investigation is too large")
            connection.execute(
                "INSERT INTO multimedia_prepared_investigations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (prepared.investigation_id, owner_identity_digest, prepared.source_plan_id,
                 prepared.source_plan_version, prepared.source_plan_integrity_digest,
                 prepared.source_intent_id, prepared.source_intent_digest,
                 prepared.source_evidence_digest, idempotency_key, request_digest, raw,
                 _prepared_digest(prepared), prepared.created_at),
            )
            connection.commit()
            return prepared, True
        except sqlite3.Error as exc:
            connection.rollback()
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_prepared_investigation(
        self, *, owner_identity_digest: str, investigation_id: str,
    ) -> PreparedInvestigation:
        _validate_owner(owner_identity_digest)
        _validate_investigation_id(investigation_id)
        connection = self._connect_existing()
        try:
            self._initialize(connection)
            row = connection.execute(
                "SELECT " + ",".join(_PREPARED_COLUMNS)
                + " FROM multimedia_prepared_investigations "
                "WHERE owner_identity_digest=? AND investigation_id=?",
                (owner_identity_digest, investigation_id),
            ).fetchone()
            if row is None:
                raise ResearchPlanUnavailableError("prepared investigation is unavailable")
            return self._decode_prepared_row(row, owner_identity_digest)
        except sqlite3.Error as exc:
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        finally:
            connection.close()

    def authorize_investigation_activation(
        self, *, owner_identity_digest: str, investigation_id: str, idempotency_key: str,
        route_policy: str, approved_ceiling_cents: int, ttl_seconds: int,
        quote_resolver: Callable[[PreparedInvestigation, str], InvestigationActivationQuote],
    ) -> tuple[InvestigationActivationAuthorization, bool]:
        _validate_owner(owner_identity_digest)
        _validate_investigation_id(investigation_id)
        _validate_key(idempotency_key)
        if route_policy not in {"cheapest", "balanced", "highest_quality"}:
            raise ResearchPlanValidationError("activation route policy is invalid")
        if (type(approved_ceiling_cents) is not int
                or not 0 < approved_ceiling_cents <= _MAX_CENTS):
            raise ResearchPlanValidationError("approved ceiling cents must be a positive integer")
        if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 86400:
            raise ResearchPlanValidationError("activation authorization ttl is invalid")
        request_digest = _digest({
            "owner_identity_digest": owner_identity_digest,
            "investigation_id": investigation_id, "idempotency_key": idempotency_key,
            "route_policy": route_policy, "approved_ceiling_cents": approved_ceiling_cents,
            "ttl_seconds": ttl_seconds,
        })
        connection = self._connect_existing()
        try:
            self._initialize(connection)
            replay_row = connection.execute(
                "SELECT " + ",".join(_AUTHORIZATION_COLUMNS)
                + " FROM multimedia_investigation_activation_authorizations "
                "WHERE owner_identity_digest=? AND investigation_id=? AND idempotency_key=?",
                (owner_identity_digest, investigation_id, idempotency_key),
            ).fetchone()
            if replay_row is not None:
                replay = self._decode_authorization_row(replay_row, owner_identity_digest, connection)
                if replay.request_digest != request_digest:
                    raise ResearchPlanError("activation authorization idempotency conflict")
                return replay, False
            prepared_snapshot = connection.execute(
                "SELECT " + ",".join(_PREPARED_COLUMNS)
                + " FROM multimedia_prepared_investigations WHERE owner_identity_digest=? "
                "AND investigation_id=?", (owner_identity_digest, investigation_id),
            ).fetchone()
            if prepared_snapshot is None:
                raise ResearchPlanUnavailableError("prepared investigation is unavailable")
            prepared = self._decode_prepared_row(prepared_snapshot, owner_identity_digest)
            existing = connection.execute(
                "SELECT 1 FROM multimedia_investigation_activation_authorizations "
                "WHERE owner_identity_digest=? AND investigation_id=?",
                (owner_identity_digest, investigation_id),
            ).fetchone()
            if existing is not None:
                raise ResearchPlanError("investigation already has activation authorization")
        except sqlite3.Error as exc:
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        finally:
            connection.close()

        quote = quote_resolver(prepared, route_policy)
        if not isinstance(quote, InvestigationActivationQuote):
            raise ResearchPlanError("activation quote is malformed")
        _assert_quote_integrity(quote, route_policy, prepared)

        connection = self._connect_existing()
        try:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            replay_row = connection.execute(
                "SELECT " + ",".join(_AUTHORIZATION_COLUMNS)
                + " FROM multimedia_investigation_activation_authorizations "
                "WHERE owner_identity_digest=? AND investigation_id=? AND idempotency_key=?",
                (owner_identity_digest, investigation_id, idempotency_key),
            ).fetchone()
            if replay_row is not None:
                replay = self._decode_authorization_row(replay_row, owner_identity_digest, connection)
                if replay.request_digest != request_digest:
                    raise ResearchPlanError("activation authorization idempotency conflict")
                connection.commit()
                return replay, False
            existing = connection.execute(
                "SELECT 1 FROM multimedia_investigation_activation_authorizations "
                "WHERE owner_identity_digest=? AND investigation_id=?",
                (owner_identity_digest, investigation_id),
            ).fetchone()
            if existing is not None:
                raise ResearchPlanError("investigation already has activation authorization")
            prepared_row = connection.execute(
                "SELECT " + ",".join(_PREPARED_COLUMNS)
                + " FROM multimedia_prepared_investigations WHERE owner_identity_digest=? "
                "AND investigation_id=?", (owner_identity_digest, investigation_id),
            ).fetchone()
            if prepared_row is None:
                raise ResearchPlanUnavailableError("prepared investigation is unavailable")
            locked_prepared = self._decode_prepared_row(prepared_row, owner_identity_digest)
            if prepared_row != prepared_snapshot or locked_prepared != prepared:
                raise ResearchPlanError("prepared investigation changed during activation")
            now = datetime.now(UTC)
            quote_issued = _parse_timestamp(quote.issued_at)
            quote_expires = _parse_timestamp(quote.expires_at)
            if quote_issued > now + timedelta(seconds=30) or now >= quote_expires:
                raise ResearchPlanError("activation quote is stale")
            expires = min(now + timedelta(seconds=ttl_seconds), quote_expires)
            if approved_ceiling_cents < quote.quoted_ceiling_cents:
                raise ResearchPlanError("approved ceiling does not cover activation quote")
            issued_at = _format_timestamp(now)
            authorization = InvestigationActivationAuthorization(
                authorization_id="mia_" + secrets.token_hex(24), investigation_id=investigation_id,
                prepared_integrity_digest=str(prepared_row[11]), source_plan_id=prepared.source_plan_id,
                source_plan_version=prepared.source_plan_version,
                source_plan_integrity_digest=prepared.source_plan_integrity_digest,
                source_intent_id=prepared.source_intent_id,
                source_intent_digest=prepared.source_intent_digest,
                source_evidence_digest=prepared.source_evidence_digest,
                total_node_count=prepared.total_node_count,
                leaf_question_count=prepared.leaf_question_count, route_policy=quote.route_policy,
                resolved_tier=quote.resolved_tier, provider=quote.provider, model=quote.model,
                dispatch_config_digest=quote.dispatch_config_digest,
                pricing_source=quote.pricing_source, pricing_digest=quote.pricing_digest,
                workload_digest=quote.workload_digest,
                quoted_ceiling_cents=quote.quoted_ceiling_cents, quote_id=quote.quote_id,
                quote_issued_at=quote.issued_at, quote_expires_at=quote.expires_at,
                quote_digest=_quote_digest(quote), approved_ceiling_cents=approved_ceiling_cents,
                ttl_seconds=ttl_seconds, request_digest=request_digest, issued_at=issued_at,
                expires_at=_format_timestamp(expires),
            )
            _assert_authorization_integrity(authorization)
            raw = _canonical(asdict(authorization))
            _check_size(raw, "activation authorization is too large")
            values = (authorization.authorization_id, owner_identity_digest, investigation_id,
                      idempotency_key, request_digest, authorization.prepared_integrity_digest,
                      authorization.source_plan_id, authorization.source_plan_version,
                      authorization.source_plan_integrity_digest, authorization.source_intent_id,
                      authorization.source_intent_digest, authorization.source_evidence_digest,
                      authorization.total_node_count, authorization.leaf_question_count,
                      authorization.route_policy, authorization.resolved_tier, authorization.provider,
                      authorization.model, authorization.dispatch_config_digest,
                      authorization.pricing_source, authorization.pricing_digest,
                      authorization.workload_digest, authorization.quoted_ceiling_cents,
                      authorization.quote_id, authorization.quote_issued_at,
                      authorization.quote_expires_at, authorization.quote_digest,
                      approved_ceiling_cents, ttl_seconds, issued_at, authorization.expires_at, raw,
                      _authorization_digest(authorization))
            connection.execute(
                "INSERT INTO multimedia_investigation_activation_authorizations VALUES ("
                + ",".join("?" for _ in values) + ")", values,
            )
            connection.commit()
            return authorization, True
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ResearchPlanError("activation authorization conflicts") from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_investigation_activation_authorization(
        self, *, owner_identity_digest: str, investigation_id: str,
    ) -> InvestigationActivationAuthorization:
        _validate_owner(owner_identity_digest)
        _validate_investigation_id(investigation_id)
        connection = self._connect_existing()
        try:
            self._initialize(connection)
            row = connection.execute(
                "SELECT " + ",".join(_AUTHORIZATION_COLUMNS)
                + " FROM multimedia_investigation_activation_authorizations "
                "WHERE owner_identity_digest=? AND investigation_id=?",
                (owner_identity_digest, investigation_id),
            ).fetchone()
            if row is None:
                raise ResearchPlanUnavailableError("activation authorization is unavailable")
            return self._decode_authorization_row(row, owner_identity_digest, connection)
        except sqlite3.Error as exc:
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        finally:
            connection.close()

    def consume_investigation_activation(
        self, *, owner_identity_digest: str, investigation_id: str,
        authorization_id: str, idempotency_key: str,
        quote_resolver: Callable[[PreparedInvestigation, str], InvestigationActivationQuote],
        supported_maximum_cents: int,
    ) -> tuple[InvestigationLaunchReservation, bool]:
        _validate_owner(owner_identity_digest)
        _validate_investigation_id(investigation_id)
        _validate_authorization_id(authorization_id)
        _validate_key(idempotency_key)
        if (type(supported_maximum_cents) is not int
                or not 1 <= supported_maximum_cents <= _MAX_CENTS):
            raise ResearchPlanValidationError("supported launch maximum is invalid")
        request_digest = _digest({
            "owner_identity_digest": owner_identity_digest,
            "investigation_id": investigation_id,
            "authorization_id": authorization_id,
            "idempotency_key": idempotency_key,
        })
        connection = self._connect_existing()
        try:
            self._initialize(connection)
            replay = self._select_launch(connection, owner_identity_digest, investigation_id)
            if replay is not None:
                reservation = self._decode_launch_row(replay, owner_identity_digest, connection)
                if (reservation.authorization_id != authorization_id
                        or replay[4] != idempotency_key
                        or reservation.request_digest != request_digest):
                    raise ResearchPlanError("activation consumption conflicts")
                return reservation, False
            authorization_row = connection.execute(
                "SELECT " + ",".join(_AUTHORIZATION_COLUMNS)
                + " FROM multimedia_investigation_activation_authorizations "
                "WHERE owner_identity_digest=? AND investigation_id=? AND authorization_id=?",
                (owner_identity_digest, investigation_id, authorization_id),
            ).fetchone()
            if authorization_row is None:
                raise ResearchPlanUnavailableError("activation authorization is unavailable")
            authorization = self._decode_authorization_row(
                authorization_row, owner_identity_digest, connection
            )
            prepared_row = connection.execute(
                "SELECT " + ",".join(_PREPARED_COLUMNS)
                + " FROM multimedia_prepared_investigations WHERE owner_identity_digest=? "
                "AND investigation_id=?", (owner_identity_digest, investigation_id),
            ).fetchone()
            if prepared_row is None:
                raise ResearchPlanUnavailableError("prepared investigation is unavailable")
            prepared = self._decode_prepared_row(prepared_row, owner_identity_digest)
        finally:
            connection.close()
        quote = quote_resolver(prepared, authorization.route_policy)
        if not isinstance(quote, InvestigationActivationQuote):
            raise ResearchPlanError("activation quote is malformed")
        _assert_quote_integrity(quote, authorization.route_policy, prepared)

        connection = self._connect_existing()
        try:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            replay = self._select_launch(connection, owner_identity_digest, investigation_id)
            if replay is not None:
                reservation = self._decode_launch_row(replay, owner_identity_digest, connection)
                if (reservation.authorization_id != authorization_id
                        or replay[4] != idempotency_key
                        or reservation.request_digest != request_digest):
                    raise ResearchPlanError("activation consumption conflicts")
                connection.commit()
                return reservation, False
            locked_auth = connection.execute(
                "SELECT " + ",".join(_AUTHORIZATION_COLUMNS)
                + " FROM multimedia_investigation_activation_authorizations "
                "WHERE owner_identity_digest=? AND investigation_id=? AND authorization_id=?",
                (owner_identity_digest, investigation_id, authorization_id),
            ).fetchone()
            locked_prepared = connection.execute(
                "SELECT " + ",".join(_PREPARED_COLUMNS)
                + " FROM multimedia_prepared_investigations WHERE owner_identity_digest=? "
                "AND investigation_id=?", (owner_identity_digest, investigation_id),
            ).fetchone()
            if locked_auth is None or locked_prepared is None:
                raise ResearchPlanUnavailableError("activation authorization is unavailable")
            current_auth = self._decode_authorization_row(
                locked_auth, owner_identity_digest, connection
            )
            self._decode_prepared_row(locked_prepared, owner_identity_digest)
            if locked_auth != authorization_row or locked_prepared != prepared_row:
                raise ResearchPlanError("activation authority changed during consumption")
            now = datetime.now(UTC)
            if now >= _parse_timestamp(current_auth.expires_at):
                raise ResearchPlanError("activation authorization is expired")
            if current_auth.approved_ceiling_cents > supported_maximum_cents:
                raise ResearchPlanError("activation ceiling exceeds supported authority")
            quote_issued, quote_expires = (
                _parse_timestamp(quote.issued_at), _parse_timestamp(quote.expires_at)
            )
            if quote_issued > now + timedelta(seconds=30) or now >= quote_expires:
                raise ResearchPlanError("activation quote is stale")
            semantic = (
                quote.route_policy, quote.resolved_tier, quote.provider, quote.model,
                quote.dispatch_config_digest, quote.pricing_source, quote.pricing_digest,
                quote.workload_digest, quote.quoted_ceiling_cents,
            )
            authorized_semantic = (
                current_auth.route_policy, current_auth.resolved_tier, current_auth.provider,
                current_auth.model, current_auth.dispatch_config_digest,
                current_auth.pricing_source, current_auth.pricing_digest,
                current_auth.workload_digest, current_auth.quoted_ceiling_cents,
            )
            if semantic != authorized_semantic:
                raise ResearchPlanError("activation quote authority drifted")
            authorization_integrity = str(locked_auth[32])
            launch_id = _derived_id(
                "multimedia-launch-reservation-v1", "mlr_", owner_identity_digest,
                authorization_id, authorization_integrity, current_auth.prepared_integrity_digest,
            )
            spend_run_id = _derived_id(
                "multimedia-spend-run-v1", "mlsr_", owner_identity_digest,
                authorization_id, authorization_integrity, current_auth.prepared_integrity_digest,
            )
            session_id = _derived_id(
                "multimedia-research-session-v1", "mls_", owner_identity_digest,
                authorization_id, authorization_integrity, current_auth.prepared_integrity_digest,
            )
            manifest_digest = _launch_manifest_digest(current_auth, authorization_integrity)
            reservation = InvestigationLaunchReservation(
                launch_reservation_id=launch_id, authorization_id=authorization_id,
                investigation_id=investigation_id,
                prepared_integrity_digest=current_auth.prepared_integrity_digest,
                authorization_integrity_digest=authorization_integrity,
                source_plan_id=current_auth.source_plan_id,
                source_plan_version=current_auth.source_plan_version,
                source_plan_integrity_digest=current_auth.source_plan_integrity_digest,
                source_intent_id=current_auth.source_intent_id,
                source_intent_digest=current_auth.source_intent_digest,
                source_evidence_digest=current_auth.source_evidence_digest,
                total_node_count=current_auth.total_node_count,
                leaf_question_count=current_auth.leaf_question_count,
                route_policy=current_auth.route_policy, resolved_tier=current_auth.resolved_tier,
                provider=current_auth.provider, model=current_auth.model,
                dispatch_config_digest=current_auth.dispatch_config_digest,
                pricing_source=current_auth.pricing_source,
                pricing_digest=current_auth.pricing_digest,
                workload_digest=current_auth.workload_digest,
                quoted_ceiling_cents=current_auth.quoted_ceiling_cents,
                approved_ceiling_cents=current_auth.approved_ceiling_cents,
                launch_manifest_digest=manifest_digest,
                request_digest=request_digest, spend_run_id=spend_run_id,
                session_id=session_id, reserved_cents=current_auth.approved_ceiling_cents,
                reserved_at=_format_timestamp(now),
            )
            raw = _canonical(asdict(reservation))
            _check_size(raw, "launch reservation is too large")
            values = (
                launch_id, owner_identity_digest, authorization_id, investigation_id,
                idempotency_key, request_digest, reservation.prepared_integrity_digest,
                reservation.authorization_integrity_digest, reservation.source_plan_id,
                reservation.source_plan_version, reservation.source_plan_integrity_digest,
                reservation.source_intent_id, reservation.source_intent_digest,
                reservation.source_evidence_digest, reservation.total_node_count,
                reservation.leaf_question_count, reservation.route_policy,
                reservation.resolved_tier, reservation.provider, reservation.model,
                reservation.dispatch_config_digest, reservation.pricing_source,
                reservation.pricing_digest, reservation.workload_digest,
                reservation.quoted_ceiling_cents, reservation.approved_ceiling_cents,
                reservation.launch_manifest_digest, spend_run_id, session_id,
                reservation.reserved_cents, reservation.reserved_at, reservation.state,
                reservation.execution_started, reservation.background_work_authorized,
                reservation.event_authority_digest, reservation.graph_authority_digest,
                reservation.provider_authority_digest, reservation.task_authority_digest,
                raw, _launch_digest(reservation),
            )
            connection.execute(
                "INSERT INTO multimedia_investigation_launch_reservations VALUES ("
                + ",".join("?" for _ in values) + ")", values,
            )
            connection.commit()
            return reservation, True
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ResearchPlanError("activation consumption conflicts") from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_investigation_launch_reservation(
        self, *, owner_identity_digest: str, investigation_id: str,
    ) -> InvestigationLaunchReservation:
        _validate_owner(owner_identity_digest)
        _validate_investigation_id(investigation_id)
        connection = self._connect_existing()
        try:
            self._initialize(connection)
            row = self._select_launch(connection, owner_identity_digest, investigation_id)
            if row is None:
                raise ResearchPlanUnavailableError("launch reservation is unavailable")
            return self._decode_launch_row(row, owner_identity_digest, connection)
        except sqlite3.Error as exc:
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        finally:
            connection.close()

    def _initialize(self, connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='multimedia_research_plans'"
        ).fetchone() is not None
        if not exists:
            if version != 0:
                raise ResearchPlanError("research plan ledger schema conflicts")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(_V2_PLAN_SCHEMA)
                connection.execute(_V2_RECEIPT_SCHEMA)
                connection.execute(_V3_PREPARED_SCHEMA)
                connection.execute(_V4_AUTHORIZATION_SCHEMA)
                connection.execute(_V5_LAUNCH_SCHEMA)
                connection.execute("PRAGMA user_version=5")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        elif version in (0, 1) and self._columns(connection, "multimedia_research_plans") == _V1_COLUMNS:
            self._migrate_v1(connection)
        elif version == 2:
            self._migrate_v2(connection)
        elif version == 3:
            self._migrate_v3(connection)
        elif version == 4:
            self._migrate_v4(connection)
        self._assert_schema(connection)

    def _migrate_v1(self, connection: sqlite3.Connection) -> None:
        self._assert_v1_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            rows = connection.execute(
                "SELECT " + ",".join(_V1_COLUMNS) + " FROM multimedia_research_plans"
            ).fetchall()
            migrated: list[tuple[Any, ...]] = []
            for row in rows:
                plan = _decode_envelope(row[8], str(row[1]), str(row[5]), allow_v1=True)
                _assert_v1_row(plan, row)
                root = deepcopy(plan.tree["root"])
                root["node_id"] = _new_node_id()
                upgraded = replace(plan, tree={"root": root})
                _assert_plan_integrity(upgraded, str(row[1]))
                raw = _encode(upgraded, str(row[1]), str(row[5]))
                _check_size(raw, "stored research plan is too large")
                migrated.append(tuple(row[:8]) + (raw,) + tuple(row[9:]) + (_plan_digest(upgraded),))
            connection.execute("ALTER TABLE multimedia_research_plans RENAME TO multimedia_research_plans_v1")
            connection.execute(_V2_PLAN_SCHEMA)
            connection.executemany(
                "INSERT INTO multimedia_research_plans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", migrated
            )
            connection.execute(_V2_RECEIPT_SCHEMA)
            connection.execute("DROP TABLE multimedia_research_plans_v1")
            connection.execute(_V3_PREPARED_SCHEMA)
            connection.execute(_V4_AUTHORIZATION_SCHEMA)
            connection.execute(_V5_LAUNCH_SCHEMA)
            connection.execute("PRAGMA user_version=5")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _migrate_v2(self, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 3:
                connection.commit()
                return
            if version != 2:
                raise ResearchPlanError("research plan ledger schema conflicts")
            self._assert_v2_schema(connection)
            connection.execute(_V3_PREPARED_SCHEMA)
            connection.execute(_V4_AUTHORIZATION_SCHEMA)
            connection.execute(_V5_LAUNCH_SCHEMA)
            connection.execute("PRAGMA user_version=5")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _migrate_v3(self, connection: sqlite3.Connection) -> None:
        self._assert_v3_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(_V4_AUTHORIZATION_SCHEMA)
            connection.execute(_V5_LAUNCH_SCHEMA)
            connection.execute("PRAGMA user_version=5")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _migrate_v4(self, connection: sqlite3.Connection) -> None:
        self._assert_v4_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(_V5_LAUNCH_SCHEMA)
            connection.execute("PRAGMA user_version=5")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _assert_v1_schema(self, connection: sqlite3.Connection) -> None:
        sql = self._schema_sql(connection, "multimedia_research_plans")
        if (self._columns(connection, "multimedia_research_plans") != _V1_COLUMNS
                or _normalized_schema(sql) != _normalized_schema(_V1_SCHEMA)):
            raise ResearchPlanError("research plan ledger schema conflicts")

    def _assert_schema(self, connection: sqlite3.Connection) -> None:
        if connection.execute("PRAGMA user_version").fetchone()[0] != 5:
            raise ResearchPlanError("research plan ledger schema conflicts")
        if (self._columns(connection, "multimedia_research_plans") != _PLAN_COLUMNS
                or self._columns(connection, "multimedia_research_plan_mutations") != _RECEIPT_COLUMNS
                or self._columns(connection, "multimedia_prepared_investigations") != _PREPARED_COLUMNS
                or self._columns(connection, "multimedia_investigation_activation_authorizations")
                != _AUTHORIZATION_COLUMNS
                or self._columns(connection, "multimedia_investigation_launch_reservations")
                != _LAUNCH_COLUMNS):
            raise ResearchPlanError("research plan ledger schema conflicts")
        plan_sql = self._schema_sql(connection, "multimedia_research_plans")
        receipt_sql = self._schema_sql(connection, "multimedia_research_plan_mutations")
        prepared_sql = self._schema_sql(connection, "multimedia_prepared_investigations")
        authorization_sql = self._schema_sql(
            connection, "multimedia_investigation_activation_authorizations"
        )
        launch_sql = self._schema_sql(connection, "multimedia_investigation_launch_reservations")
        if (_normalized_schema(plan_sql) != _normalized_schema(_V2_PLAN_SCHEMA)
                or _normalized_schema(receipt_sql) != _normalized_schema(_V2_RECEIPT_SCHEMA)
                or _normalized_schema(prepared_sql) != _normalized_schema(_V3_PREPARED_SCHEMA)
                or _normalized_schema(authorization_sql)
                != _normalized_schema(_V4_AUTHORIZATION_SCHEMA)
                or _normalized_schema(launch_sql) != _normalized_schema(_V5_LAUNCH_SCHEMA)):
            raise ResearchPlanError("research plan ledger schema conflicts")

    def _assert_v4_schema(self, connection: sqlite3.Connection) -> None:
        if connection.execute("PRAGMA user_version").fetchone()[0] != 4:
            raise ResearchPlanError("research plan ledger schema conflicts")
        if (self._columns(connection, "multimedia_research_plans") != _PLAN_COLUMNS
                or self._columns(connection, "multimedia_research_plan_mutations") != _RECEIPT_COLUMNS
                or self._columns(connection, "multimedia_prepared_investigations") != _PREPARED_COLUMNS
                or self._columns(connection, "multimedia_investigation_activation_authorizations")
                != _AUTHORIZATION_COLUMNS
                or _normalized_schema(self._schema_sql(connection, "multimedia_research_plans"))
                != _normalized_schema(_V2_PLAN_SCHEMA)
                or _normalized_schema(self._schema_sql(connection, "multimedia_research_plan_mutations"))
                != _normalized_schema(_V2_RECEIPT_SCHEMA)
                or _normalized_schema(self._schema_sql(connection, "multimedia_prepared_investigations"))
                != _normalized_schema(_V3_PREPARED_SCHEMA)
                or _normalized_schema(self._schema_sql(connection, "multimedia_investigation_activation_authorizations"))
                != _normalized_schema(_V4_AUTHORIZATION_SCHEMA)
                or self._schema_sql(connection, "multimedia_investigation_launch_reservations")):
            raise ResearchPlanError("research plan ledger schema conflicts")

    def _assert_v3_schema(self, connection: sqlite3.Connection) -> None:
        if connection.execute("PRAGMA user_version").fetchone()[0] != 3:
            raise ResearchPlanError("research plan ledger schema conflicts")
        if (self._columns(connection, "multimedia_research_plans") != _PLAN_COLUMNS
                or self._columns(connection, "multimedia_research_plan_mutations") != _RECEIPT_COLUMNS
                or self._columns(connection, "multimedia_prepared_investigations") != _PREPARED_COLUMNS
                or _normalized_schema(self._schema_sql(connection, "multimedia_research_plans"))
                != _normalized_schema(_V2_PLAN_SCHEMA)
                or _normalized_schema(self._schema_sql(connection, "multimedia_research_plan_mutations"))
                != _normalized_schema(_V2_RECEIPT_SCHEMA)
                or _normalized_schema(self._schema_sql(connection, "multimedia_prepared_investigations"))
                != _normalized_schema(_V3_PREPARED_SCHEMA)
                or self._schema_sql(connection, "multimedia_investigation_activation_authorizations")):
            raise ResearchPlanError("research plan ledger schema conflicts")

    def _assert_v2_schema(self, connection: sqlite3.Connection) -> None:
        if (self._columns(connection, "multimedia_research_plans") != _PLAN_COLUMNS
                or self._columns(connection, "multimedia_research_plan_mutations") != _RECEIPT_COLUMNS
                or _normalized_schema(self._schema_sql(connection, "multimedia_research_plans"))
                != _normalized_schema(_V2_PLAN_SCHEMA)
                or _normalized_schema(self._schema_sql(connection, "multimedia_research_plan_mutations"))
                != _normalized_schema(_V2_RECEIPT_SCHEMA)
                or self._schema_sql(connection, "multimedia_prepared_investigations")):
            raise ResearchPlanError("research plan ledger schema conflicts")

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
        return tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))

    @staticmethod
    def _schema_sql(connection: sqlite3.Connection, table: str) -> str:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return "" if row is None else str(row[0])

    @staticmethod
    def _select_plan(connection: sqlite3.Connection, owner: str, plan_id: str):
        return connection.execute(
            "SELECT " + ",".join(_PLAN_COLUMNS) + " FROM multimedia_research_plans "
            "WHERE owner_identity_digest=? AND plan_id=?", (owner, plan_id)
        ).fetchone()

    @staticmethod
    def _select_launch(connection: sqlite3.Connection, owner: str, investigation_id: str):
        return connection.execute(
            "SELECT " + ",".join(_LAUNCH_COLUMNS)
            + " FROM multimedia_investigation_launch_reservations "
            "WHERE owner_identity_digest=? AND investigation_id=?",
            (owner, investigation_id),
        ).fetchone()

    @staticmethod
    def _decode_launch_row(
        row: tuple[object, ...], owner: str, connection: sqlite3.Connection,
    ) -> InvestigationLaunchReservation:
        fields = dict(zip(_LAUNCH_COLUMNS, row, strict=True))
        try:
            raw = fields["reservation_json"]
            if not isinstance(raw, str) or len(raw.encode()) > _MAX_RECORD_BYTES:
                raise ValueError
            value = json.loads(raw)
            if (not isinstance(value, dict)
                    or set(value) != set(InvestigationLaunchReservation.__dataclass_fields__)):
                raise ValueError
            reservation = InvestigationLaunchReservation(**value)
            _assert_launch_integrity(reservation)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchPlanError("stored launch reservation is malformed") from exc
        authorization_row = connection.execute(
            "SELECT " + ",".join(_AUTHORIZATION_COLUMNS)
            + " FROM multimedia_investigation_activation_authorizations "
            "WHERE owner_identity_digest=? AND investigation_id=? AND authorization_id=?",
            (owner, reservation.investigation_id, reservation.authorization_id),
        ).fetchone()
        if authorization_row is None:
            raise ResearchPlanError("stored launch reservation integrity conflicts")
        authorization = ResearchPlanLedger._decode_authorization_row(
            authorization_row, owner, connection
        )
        request_digest = _digest({
            "owner_identity_digest": owner,
            "investigation_id": reservation.investigation_id,
            "authorization_id": reservation.authorization_id,
            "idempotency_key": fields["idempotency_key"],
        })
        auth_digest = str(authorization_row[32])
        identities = (
            _derived_id("multimedia-launch-reservation-v1", "mlr_", owner,
                        reservation.authorization_id, auth_digest,
                        authorization.prepared_integrity_digest),
            _derived_id("multimedia-spend-run-v1", "mlsr_", owner,
                        reservation.authorization_id, auth_digest,
                        authorization.prepared_integrity_digest),
            _derived_id("multimedia-research-session-v1", "mls_", owner,
                        reservation.authorization_id, auth_digest,
                        authorization.prepared_integrity_digest),
        )
        scalar_fields = {
            name: getattr(reservation, name) for name in
            InvestigationLaunchReservation.__dataclass_fields__
        }
        scalar_fields.update({
            "owner_identity_digest": owner,
            "idempotency_key": fields["idempotency_key"],
            "reservation_json": _canonical(asdict(reservation)),
            "reservation_integrity_digest": _launch_digest(reservation),
        })
        expected = tuple(scalar_fields[name] for name in _LAUNCH_COLUMNS)
        reserved_at = _parse_timestamp(reservation.reserved_at)
        issued_at = _parse_timestamp(authorization.issued_at)
        expires_at = _parse_timestamp(authorization.expires_at)
        if (not _valid_key(fields["idempotency_key"]) or tuple(row) != expected
                or reservation.request_digest != request_digest
                or identities != (reservation.launch_reservation_id,
                                   reservation.spend_run_id, reservation.session_id)
                or reservation.launch_manifest_digest
                != _launch_manifest_digest(authorization, auth_digest)
                or reservation.reserved_cents != authorization.approved_ceiling_cents
                or not issued_at <= reserved_at < expires_at):
            raise ResearchPlanError("stored launch reservation integrity conflicts")
        return reservation

    @staticmethod
    def _decode_row(row: tuple[object, ...], owner: str) -> ResearchPlan:
        plan = _decode_envelope(row[8], owner, str(row[5]))
        expected = (
            plan.plan_id, owner, plan.source_intent_id, plan.source_intent_digest,
            plan.source_evidence_digest, row[5], plan.request_digest, plan.plan_version,
            row[8], plan.created_at, plan.updated_at, _plan_digest(plan),
        )
        if tuple(row) != expected:
            raise ResearchPlanError("stored research plan integrity conflicts")
        return plan

    @staticmethod
    def _decode_receipt(row: tuple[object, ...], owner: str) -> ResearchPlan:
        if not isinstance(row[8], str) or len(row[8].encode()) > _MAX_RECORD_BYTES:
            raise ResearchPlanError("stored research plan mutation is too large")
        try:
            value = json.loads(str(row[8]))
            if not isinstance(value, dict) or set(value) != set(ResearchPlan.__dataclass_fields__):
                raise ValueError
            plan = ResearchPlan(**value)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchPlanError("stored research plan mutation is malformed") from exc
        try:
            _assert_plan_integrity(plan, owner)
        except ResearchPlanError as exc:
            raise ResearchPlanError("stored research plan mutation integrity conflicts") from exc
        if (row[0] != owner or row[1] != plan.plan_id or not _valid_key(row[2])
                or not _hex_digest(row[3]) or row[5] != plan.plan_version
                or type(row[4]) is not int or row[5] != row[4] + 1
                or not _hex_digest(row[6]) or row[7] != _plan_digest(plan)
                or not _timestamp(row[9]) or str(row[8]) != _canonical(asdict(plan))):
            raise ResearchPlanError("stored research plan mutation integrity conflicts")
        return plan

    @staticmethod
    def _decode_prepared_row(row: tuple[object, ...], owner: str) -> PreparedInvestigation:
        prepared = _decode_prepared_envelope(row[10], owner, str(row[8]))
        expected = (
            prepared.investigation_id, owner, prepared.source_plan_id,
            prepared.source_plan_version, prepared.source_plan_integrity_digest,
            prepared.source_intent_id, prepared.source_intent_digest,
            prepared.source_evidence_digest, row[8], prepared.request_digest, row[10],
            _prepared_digest(prepared), prepared.created_at,
        )
        if not _valid_key(row[8]) or tuple(row) != expected:
            raise ResearchPlanError("stored prepared investigation integrity conflicts")
        return prepared

    @staticmethod
    def _decode_authorization_row(
        row: tuple[object, ...], owner: str, connection: sqlite3.Connection,
    ) -> InvestigationActivationAuthorization:
        try:
            value = json.loads(str(row[31]))
            if (not isinstance(value, dict)
                    or set(value) != set(InvestigationActivationAuthorization.__dataclass_fields__)):
                raise ValueError
            authorization = InvestigationActivationAuthorization(**value)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchPlanError("stored activation authorization is malformed") from exc
        _assert_authorization_integrity(authorization)
        expected = (authorization.authorization_id, owner, authorization.investigation_id, row[3],
                    authorization.request_digest, authorization.prepared_integrity_digest,
                    authorization.source_plan_id, authorization.source_plan_version,
                    authorization.source_plan_integrity_digest, authorization.source_intent_id,
                    authorization.source_intent_digest, authorization.source_evidence_digest,
                    authorization.total_node_count, authorization.leaf_question_count,
                    authorization.route_policy, authorization.resolved_tier, authorization.provider,
                    authorization.model, authorization.dispatch_config_digest,
                    authorization.pricing_source, authorization.pricing_digest,
                    authorization.workload_digest, authorization.quoted_ceiling_cents,
                    authorization.quote_id, authorization.quote_issued_at,
                    authorization.quote_expires_at, authorization.quote_digest,
                    authorization.approved_ceiling_cents, authorization.ttl_seconds,
                    authorization.issued_at,
                    authorization.expires_at, _canonical(asdict(authorization)),
                    _authorization_digest(authorization))
        prepared_row = connection.execute(
            "SELECT " + ",".join(_PREPARED_COLUMNS)
            + " FROM multimedia_prepared_investigations WHERE owner_identity_digest=? "
            "AND investigation_id=?", (owner, authorization.investigation_id),
        ).fetchone()
        expected_request_digest = _digest({
            "owner_identity_digest": owner, "investigation_id": authorization.investigation_id,
            "idempotency_key": row[3], "route_policy": authorization.route_policy,
            "approved_ceiling_cents": authorization.approved_ceiling_cents,
            "ttl_seconds": authorization.ttl_seconds,
        })
        if (not _valid_key(row[3]) or authorization.request_digest != expected_request_digest
                or tuple(row) != expected or prepared_row is None
                or str(prepared_row[11]) != authorization.prepared_integrity_digest):
            raise ResearchPlanError("stored activation authorization integrity conflicts")
        prepared = ResearchPlanLedger._decode_prepared_row(prepared_row, owner)
        if (prepared.source_plan_id != authorization.source_plan_id
                or prepared.source_plan_version != authorization.source_plan_version
                or prepared.source_plan_integrity_digest != authorization.source_plan_integrity_digest
                or prepared.source_intent_id != authorization.source_intent_id
                or prepared.source_intent_digest != authorization.source_intent_digest
                or prepared.source_evidence_digest != authorization.source_evidence_digest
                or prepared.total_node_count != authorization.total_node_count
                or prepared.leaf_question_count != authorization.leaf_question_count):
            raise ResearchPlanError("stored activation authorization integrity conflicts")
        return authorization

    def _connect_existing(self) -> sqlite3.Connection:
        if not self.path.is_file() or self.path.is_symlink():
            raise ResearchPlanUnavailableError("research plan is unavailable")
        return self._connect()

    def _connect(self) -> sqlite3.Connection:
        if self.path.is_symlink():
            raise ResearchPlanError("research plan ledger path is unsafe")
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            except OSError as exc:
                raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
            else:
                os.close(fd)
        try:
            fd = os.open(self.path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        try:
            metadata = os.fstat(fd)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or stat.S_IMODE(metadata.st_mode) & 0o077):
                raise ResearchPlanError("research plan ledger path is unsafe")
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            connection.execute("PRAGMA foreign_keys=ON")
            reopened = self.path.stat(follow_symlinks=False)
            if (reopened.st_dev, reopened.st_ino) != (metadata.st_dev, metadata.st_ino):
                connection.close()
                raise ResearchPlanError("research plan ledger path changed during open")
            return connection
        finally:
            os.close(fd)


def _validate_operations(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_OPERATIONS:
        raise ResearchPlanValidationError("research plan edit operations are invalid")
    result: list[dict[str, object]] = []
    shapes = {
        "add_child": {"type", "parent_node_id", "position", "question"},
        "update_question": {"type", "node_id", "question"},
        "move_subtree": {"type", "node_id", "new_parent_node_id", "position"},
        "remove_subtree": {"type", "node_id"},
    }
    for operation in value:
        if not isinstance(operation, dict) or type(operation.get("type")) is not str:
            raise ResearchPlanValidationError("research plan edit operation is malformed")
        kind = operation["type"]
        if kind not in shapes or set(operation) != shapes[kind]:
            raise ResearchPlanValidationError("research plan edit operation is malformed")
        normalized = dict(operation)
        for field in ("node_id", "parent_node_id", "new_parent_node_id"):
            if field in normalized and not _opaque_id(normalized[field], prefix="mrpn_", hex_length=48):
                raise ResearchPlanValidationError("research plan edit node identity is invalid")
        if "position" in normalized and (type(normalized["position"]) is not int or normalized["position"] < 0):
            raise ResearchPlanValidationError("research plan edit position is invalid")
        if "question" in normalized:
            question = normalized["question"]
            if not isinstance(question, str):
                raise ResearchPlanValidationError("research plan edit question is invalid")
            question = question.strip()
            if not 3 <= len(question) <= 2000:
                raise ResearchPlanValidationError("research plan edit question is invalid")
            normalized["question"] = question
        result.append(normalized)
    return result


def _apply_operation(tree: dict[str, object], operation: dict[str, object]) -> None:
    root = tree["root"]
    assert isinstance(root, dict)
    nodes, parents = _index_tree(root)
    kind = operation["type"]
    node_id = operation.get("node_id")
    if node_id == root["node_id"]:
        raise ResearchPlanValidationError("research plan root cannot be edited")
    if kind == "add_child":
        parent = nodes.get(operation["parent_node_id"])
        if parent is None:
            raise ResearchPlanValidationError("research plan edit target is unavailable")
        children = parent["children"]
        position = operation["position"]
        if not isinstance(children, list) or not isinstance(position, int) or position > len(children):
            raise ResearchPlanValidationError("research plan edit position is invalid")
        children.insert(position, {"node_id": _new_node_id(), "kind": "research_question",
                                   "question": operation["question"], "children": []})
    elif kind == "update_question":
        node = nodes.get(node_id)
        if node is None:
            raise ResearchPlanValidationError("research plan edit target is unavailable")
        if node["question"] == operation["question"]:
            raise ResearchPlanValidationError("research plan edit is a no-op")
        node["question"] = operation["question"]
    elif kind == "remove_subtree":
        if node_id not in nodes:
            raise ResearchPlanValidationError("research plan edit target is unavailable")
        parent = parents[node_id]
        parent["children"] = [child for child in parent["children"] if child["node_id"] != node_id]
    elif kind == "move_subtree":
        node = nodes.get(node_id)
        destination = nodes.get(operation["new_parent_node_id"])
        if node is None or destination is None:
            raise ResearchPlanValidationError("research plan edit target is unavailable")
        descendants, _ = _index_tree(node)
        if destination["node_id"] in descendants:
            raise ResearchPlanValidationError("research plan edit would create a cycle")
        old_parent = parents[node_id]
        old_children = old_parent["children"]
        old_position = next(i for i, child in enumerate(old_children) if child["node_id"] == node_id)
        old_children.pop(old_position)
        destination_children = destination["children"]
        position = operation["position"]
        if not isinstance(position, int) or position > len(destination_children):
            raise ResearchPlanValidationError("research plan edit position is invalid")
        if old_parent is destination and old_position == position:
            raise ResearchPlanValidationError("research plan edit is a no-op")
        destination_children.insert(position, node)


def _index_tree(root: dict[str, object]) -> tuple[dict[object, dict[str, object]], dict[object, dict[str, object]]]:
    nodes: dict[object, dict[str, object]] = {}
    parents: dict[object, dict[str, object]] = {}
    stack: list[tuple[dict[str, object], dict[str, object] | None]] = [(root, None)]
    while stack:
        node, parent = stack.pop()
        identity = node.get("node_id")
        if identity in nodes:
            raise ResearchPlanError("stored research plan tree conflicts")
        nodes[identity] = node
        if parent is not None:
            parents[identity] = parent
        children = node.get("children")
        if isinstance(children, list):
            for child in reversed(children):
                if not isinstance(child, dict):
                    raise ResearchPlanError("stored research plan tree conflicts")
                stack.append((child, node))
    return nodes, parents


def _validate_tree(tree: object, plan: ResearchPlan) -> None:
    if not isinstance(tree, dict) or set(tree) != {"root"} or not isinstance(tree["root"], dict):
        raise ResearchPlanValidationError("research plan tree conflicts")
    root = tree["root"]
    stack: list[tuple[dict[str, object], int, bool]] = [(root, 1, True)]
    identities: set[str] = set()
    count = 0
    while stack:
        node, depth, is_root = stack.pop()
        count += 1
        allowed = {"node_id", "kind", "question", "children"}
        if is_root:
            allowed |= {"source_intent_id", "source_intent_digest", "source_evidence_digest"}
        question = node.get("question")
        children = node.get("children")
        identity = node.get("node_id")
        if (set(node) != allowed or not _opaque_id(identity, prefix="mrpn_", hex_length=48)
                or identity in identities or node.get("kind") != "research_question"
                or not isinstance(question, str) or question != question.strip()
                or not 3 <= len(question) <= 2000 or not isinstance(children, list)
                or len(children) > _MAX_CHILDREN or depth > _MAX_DEPTH or count > _MAX_NODES):
            raise ResearchPlanValidationError("research plan tree conflicts")
        identities.add(identity)
        if is_root and (node.get("source_intent_id") != plan.source_intent_id
                        or node.get("source_intent_digest") != plan.source_intent_digest
                        or node.get("source_evidence_digest") != plan.source_evidence_digest):
            raise ResearchPlanValidationError("research plan tree conflicts")
        for child in reversed(children):
            if not isinstance(child, dict):
                raise ResearchPlanValidationError("research plan tree conflicts")
            stack.append((child, depth + 1, False))


def _assert_plan_integrity(plan: ResearchPlan, owner: str) -> None:
    try:
        _validate_tree(plan.tree, plan)
        root = plan.tree["root"]
        assert isinstance(root, dict)
        expected_request = _digest({
            "source_intent_id": plan.source_intent_id,
            "source_intent_digest": plan.source_intent_digest,
            "source_evidence_digest": plan.source_evidence_digest,
            "question": root["question"],
        })
    except ResearchPlanError:
        raise
    except (KeyError, TypeError, AssertionError) as exc:
        raise ResearchPlanError("stored research plan is malformed") from exc
    if (not _opaque_id(plan.plan_id, prefix="mrp_", hex_length=48)
            or not _opaque_id(plan.source_intent_id, prefix="mmri_", hex_length=48)
            or not _hex_digest(plan.source_intent_digest)
            or not _hex_digest(plan.source_evidence_digest) or plan.request_digest != expected_request
            or type(plan.plan_version) is not int or plan.plan_version < 1
            or plan.state not in {"draft", "approved"} or not _timestamp(plan.created_at)
            or not _timestamp(plan.updated_at) or plan.research_launched is not False
            or plan.provider_launch_authorized is not False or plan.spend_authority_digest is not None
            or (plan.state == "draft" and (plan.approved_at is not None
                                             or plan.approved_by_owner_digest is not None))
            or (plan.state == "approved" and (not _timestamp(plan.approved_at)
                                                or plan.approved_by_owner_digest != owner))):
        raise ResearchPlanError("stored research plan integrity conflicts")


def _assert_v1_row(plan: ResearchPlan, row: tuple[object, ...]) -> None:
    root = plan.tree.get("root") if isinstance(plan.tree, dict) else None
    if (not isinstance(root, dict) or set(root) != {
        "kind", "question", "source_intent_id", "source_intent_digest",
        "source_evidence_digest", "children",
    } or root.get("children") != [] or plan.plan_version != 1
            or tuple(row[:8]) != (plan.plan_id, row[1], plan.source_intent_id,
                                  plan.source_intent_digest, plan.source_evidence_digest,
                                  row[5], plan.request_digest, plan.plan_version)
            or tuple(row[9:]) != (plan.created_at, plan.updated_at)):
        raise ResearchPlanError("stored research plan integrity conflicts")
    upgraded = replace(plan, tree={"root": {**root, "node_id": "mrpn_" + "0" * 48}})
    _assert_plan_integrity(upgraded, str(row[1]))


def _decode_envelope(raw: object, owner: str, key: str, *, allow_v1: bool = False) -> ResearchPlan:
    if not isinstance(raw, str) or len(raw.encode()) > _MAX_RECORD_BYTES:
        raise ResearchPlanError("stored research plan is too large")
    try:
        envelope = json.loads(raw)
        if (not isinstance(envelope, dict) or set(envelope) != {
            "owner_identity_digest", "idempotency_key", "plan"
        } or envelope["owner_identity_digest"] != owner or envelope["idempotency_key"] != key
                or not isinstance(envelope["plan"], dict)
                or set(envelope["plan"]) != set(ResearchPlan.__dataclass_fields__)):
            raise ResearchPlanError("stored research plan binding conflicts")
        plan = ResearchPlan(**envelope["plan"])
    except ResearchPlanError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ResearchPlanError("stored research plan is malformed") from exc
    if not allow_v1:
        try:
            _assert_plan_integrity(plan, owner)
        except ResearchPlanError as exc:
            raise ResearchPlanError("stored research plan integrity conflicts") from exc
    return plan


def _encode(plan: ResearchPlan, owner: str, key: str) -> str:
    return _canonical({"owner_identity_digest": owner, "idempotency_key": key, "plan": asdict(plan)})


def _plan_digest(plan: ResearchPlan) -> str:
    return _digest(asdict(plan))


def _encode_prepared(prepared: PreparedInvestigation, owner: str, key: str) -> str:
    return _canonical({
        "owner_identity_digest": owner,
        "idempotency_key": key,
        "prepared_investigation": asdict(prepared),
    })


def _decode_prepared_envelope(raw: object, owner: str, key: str) -> PreparedInvestigation:
    if not isinstance(raw, str) or len(raw.encode()) > _MAX_RECORD_BYTES:
        raise ResearchPlanError("stored prepared investigation is too large")
    try:
        envelope = json.loads(raw)
        if (not isinstance(envelope, dict) or set(envelope) != {
                "owner_identity_digest", "idempotency_key", "prepared_investigation"
        } or envelope["owner_identity_digest"] != owner or envelope["idempotency_key"] != key
                or not isinstance(envelope["prepared_investigation"], dict)
                or set(envelope["prepared_investigation"])
                != set(PreparedInvestigation.__dataclass_fields__)):
            raise ResearchPlanError("stored prepared investigation binding conflicts")
        prepared = PreparedInvestigation(**envelope["prepared_investigation"])
        _assert_prepared_integrity(prepared)
        if raw != _encode_prepared(prepared, owner, key):
            raise ResearchPlanError("stored prepared investigation is non-canonical")
        return prepared
    except ResearchPlanError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ResearchPlanError("stored prepared investigation is malformed") from exc


def _prepared_digest(prepared: PreparedInvestigation) -> str:
    return _digest(asdict(prepared))


def _tree_counts(tree: dict[str, object]) -> tuple[int, int]:
    root = tree["root"]
    assert isinstance(root, dict)
    nodes, _ = _index_tree(root)
    leaves = sum(not node["children"] for node in nodes.values())
    return len(nodes), leaves


def _assert_prepared_integrity(prepared: PreparedInvestigation) -> None:
    plan_shape = ResearchPlan(
        plan_id=prepared.source_plan_id, source_intent_id=prepared.source_intent_id,
        source_intent_digest=prepared.source_intent_digest,
        source_evidence_digest=prepared.source_evidence_digest, request_digest="0" * 64,
        state="approved", plan_version=prepared.source_plan_version, tree=prepared.tree,
        created_at=prepared.created_at, updated_at=prepared.created_at,
        approved_at=prepared.created_at, approved_by_owner_digest="0" * 64,
    )
    try:
        _validate_tree(prepared.tree, plan_shape)
        counts = _tree_counts(prepared.tree)
    except ResearchPlanError:
        raise
    except (KeyError, TypeError, AssertionError) as exc:
        raise ResearchPlanError("stored prepared investigation is malformed") from exc
    expected_request_digest = _digest({
        "expected_plan_version": prepared.source_plan_version,
        "source_plan_id": prepared.source_plan_id,
    })
    if (not _opaque_id(prepared.investigation_id, prefix="mpi_", hex_length=48)
            or not _opaque_id(prepared.source_plan_id, prefix="mrp_", hex_length=48)
            or type(prepared.source_plan_version) is not int or prepared.source_plan_version < 1
            or not _hex_digest(prepared.source_plan_integrity_digest)
            or not _opaque_id(prepared.source_intent_id, prefix="mmri_", hex_length=48)
            or not _hex_digest(prepared.source_intent_digest)
            or not _hex_digest(prepared.source_evidence_digest)
            or type(prepared.total_node_count) is not int
            or type(prepared.leaf_question_count) is not int
            or counts != (prepared.total_node_count, prepared.leaf_question_count)
            or prepared.request_digest != expected_request_digest or prepared.state != "prepared"
            or not _timestamp(prepared.created_at) or prepared.execution_started is not False
            or prepared.background_work_authorized is not False
            or prepared.event_authority_digest is not None
            or prepared.graph_authority_digest is not None
            or prepared.provider_authority_digest is not None
            or prepared.spend_authority_digest is not None):
        raise ResearchPlanError("stored prepared investigation integrity conflicts")


def _quote_digest(quote: InvestigationActivationQuote) -> str:
    return _digest(asdict(quote))


def _authorization_digest(authorization: InvestigationActivationAuthorization) -> str:
    return _digest(asdict(authorization))


def _assert_quote_integrity(
    quote: InvestigationActivationQuote, route_policy: str, prepared: PreparedInvestigation,
) -> None:
    try:
        issued = _parse_timestamp(quote.issued_at)
        expires = _parse_timestamp(quote.expires_at)
    except (TypeError, ValueError) as exc:
        raise ResearchPlanError("activation quote is malformed") from exc
    workload_digest = _digest({
        "investigation_id": prepared.investigation_id,
        "prepared_integrity_digest": _prepared_digest(prepared),
        "total_node_count": prepared.total_node_count,
        "leaf_question_count": prepared.leaf_question_count,
    })
    text_fields = (quote.resolved_tier, quote.provider, quote.model, quote.pricing_source,
                   quote.quote_id)
    if (quote.schema_version != 1 or quote.route_policy != route_policy
            or any(not isinstance(value, str) or not value or len(value) > 256 for value in text_fields)
            or not _hex_digest(quote.dispatch_config_digest)
            or not _hex_digest(quote.pricing_digest) or quote.workload_digest != workload_digest
            or type(quote.quoted_ceiling_cents) is not int
            or not 0 < quote.quoted_ceiling_cents <= _MAX_CENTS
            or expires <= issued or expires - issued > timedelta(hours=24)):
        raise ResearchPlanError("activation quote integrity conflicts")


def _assert_authorization_integrity(
    authorization: InvestigationActivationAuthorization,
) -> None:
    try:
        issued = _parse_timestamp(authorization.issued_at)
        expires = _parse_timestamp(authorization.expires_at)
        quote_issued = _parse_timestamp(authorization.quote_issued_at)
        quote_expires = _parse_timestamp(authorization.quote_expires_at)
        quote = InvestigationActivationQuote(
            schema_version=1, route_policy=authorization.route_policy,
            resolved_tier=authorization.resolved_tier, provider=authorization.provider,
            model=authorization.model, dispatch_config_digest=authorization.dispatch_config_digest,
            pricing_source=authorization.pricing_source, pricing_digest=authorization.pricing_digest,
            workload_digest=authorization.workload_digest,
            quoted_ceiling_cents=authorization.quoted_ceiling_cents,
            quote_id=authorization.quote_id, issued_at=authorization.quote_issued_at,
            expires_at=authorization.quote_expires_at,
        )
    except (TypeError, ValueError) as exc:
        raise ResearchPlanError("stored activation authorization is malformed") from exc
    text_fields = (authorization.resolved_tier, authorization.provider, authorization.model,
                   authorization.pricing_source, authorization.quote_id)
    if (not _opaque_id(authorization.authorization_id, prefix="mia_", hex_length=48)
            or not _opaque_id(authorization.investigation_id, prefix="mpi_", hex_length=48)
            or not _hex_digest(authorization.prepared_integrity_digest)
            or not _opaque_id(authorization.source_plan_id, prefix="mrp_", hex_length=48)
            or type(authorization.source_plan_version) is not int
            or authorization.source_plan_version < 1
            or not _hex_digest(authorization.source_plan_integrity_digest)
            or not _opaque_id(authorization.source_intent_id, prefix="mmri_", hex_length=48)
            or not _hex_digest(authorization.source_intent_digest)
            or not _hex_digest(authorization.source_evidence_digest)
            or type(authorization.total_node_count) is not int
            or type(authorization.leaf_question_count) is not int
            or authorization.total_node_count < 1 or authorization.leaf_question_count < 1
            or authorization.route_policy not in {"cheapest", "balanced", "highest_quality"}
            or any(not isinstance(value, str) or not value or len(value) > 256 for value in text_fields)
            or not _hex_digest(authorization.dispatch_config_digest)
            or not _hex_digest(authorization.pricing_digest)
            or not _hex_digest(authorization.workload_digest)
            or type(authorization.quoted_ceiling_cents) is not int
            or not 0 < authorization.quoted_ceiling_cents <= _MAX_CENTS
            or authorization.quote_digest != _quote_digest(quote)
            or type(authorization.approved_ceiling_cents) is not int
            or authorization.approved_ceiling_cents > _MAX_CENTS
            or authorization.approved_ceiling_cents < authorization.quoted_ceiling_cents
            or type(authorization.ttl_seconds) is not int
            or not 60 <= authorization.ttl_seconds <= 86400
            or not _hex_digest(authorization.request_digest) or expires <= issued
            or expires != min(
                issued + timedelta(seconds=authorization.ttl_seconds), quote_expires
            ) or quote_expires <= quote_issued
            or quote_expires - quote_issued > timedelta(hours=24)
            or authorization.state != "authorized" or authorization.execution_started is not False
            or authorization.event_authority_digest is not None
            or authorization.graph_authority_digest is not None
            or authorization.provider_authority_digest is not None
            or authorization.spend_reservation_digest is not None
            or authorization.consumed_at is not None
            or authorization.background_work_authorized is not False):
        raise ResearchPlanError("stored activation authorization integrity conflicts")


def _validate_owner(value: str) -> None:
    if not _hex_digest(value):
        raise ResearchPlanError("research plan owner identity is invalid")


def _validate_plan_id(value: object) -> None:
    if not _opaque_id(value, prefix="mrp_", hex_length=48):
        raise ResearchPlanUnavailableError("research plan is unavailable")


def _validate_investigation_id(value: object) -> None:
    if not _opaque_id(value, prefix="mpi_", hex_length=48):
        raise ResearchPlanUnavailableError("prepared investigation is unavailable")


def _validate_authorization_id(value: object) -> None:
    if not _opaque_id(value, prefix="mia_", hex_length=48):
        raise ResearchPlanUnavailableError("activation authorization is unavailable")


def _valid_key(value: object) -> bool:
    return (isinstance(value, str) and 16 <= len(value) <= 128
            and all(character.isascii() and (character.isalnum() or character in "_-") for character in value))


def _validate_key(value: object) -> None:
    if not _valid_key(value):
        raise ResearchPlanError("research plan idempotency key is invalid")


def _validate_version(value: object) -> None:
    if type(value) is not int or value < 1:
        raise ResearchPlanError("research plan version is invalid")


def _check_size(raw: str, message: str) -> None:
    if len(raw.encode()) > _MAX_RECORD_BYTES:
        raise ResearchPlanTooLargeError(message)


def _hex_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _opaque_id(value: object, *, prefix: str, hex_length: int) -> bool:
    return (isinstance(value, str) and value.startswith(prefix)
            and len(value) == len(prefix) + hex_length
            and all(c in "0123456789abcdef" for c in value[len(prefix):]))


def _timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").tzinfo is not None
    except ValueError:
        return False


def _parse_timestamp(value: object) -> datetime:
    if not _timestamp(value):
        raise ValueError("invalid UTC timestamp")
    assert isinstance(value, str)
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalized_schema(value: str) -> str:
    return "".join(value.lower().split()).replace("ifnotexists", "")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _launch_digest(reservation: InvestigationLaunchReservation) -> str:
    return _digest({"domain": "multimedia-investigation-launch-reservation-v1",
                    "reservation": asdict(reservation)})


def _launch_manifest_digest(
    authorization: InvestigationActivationAuthorization, authorization_integrity_digest: str,
) -> str:
    return _digest({
        "domain": "multimedia-investigation-launch-manifest-v1",
        "prepared_integrity_digest": authorization.prepared_integrity_digest,
        "authorization_integrity_digest": authorization_integrity_digest,
        "source_plan_id": authorization.source_plan_id,
        "source_plan_version": authorization.source_plan_version,
        "source_plan_integrity_digest": authorization.source_plan_integrity_digest,
        "source_intent_id": authorization.source_intent_id,
        "source_intent_digest": authorization.source_intent_digest,
        "source_evidence_digest": authorization.source_evidence_digest,
        "total_node_count": authorization.total_node_count,
        "leaf_question_count": authorization.leaf_question_count,
        "route_policy": authorization.route_policy,
        "resolved_tier": authorization.resolved_tier,
        "provider": authorization.provider,
        "model": authorization.model,
        "dispatch_config_digest": authorization.dispatch_config_digest,
        "pricing_source": authorization.pricing_source,
        "pricing_digest": authorization.pricing_digest,
        "workload_digest": authorization.workload_digest,
        "quoted_ceiling_cents": authorization.quoted_ceiling_cents,
        "approved_ceiling_cents": authorization.approved_ceiling_cents,
    })


def _assert_launch_integrity(reservation: InvestigationLaunchReservation) -> None:
    text_fields = (
        reservation.route_policy, reservation.resolved_tier, reservation.provider,
        reservation.model, reservation.pricing_source,
    )
    if (not _opaque_id(reservation.launch_reservation_id, prefix="mlr_", hex_length=48)
            or not _opaque_id(reservation.authorization_id, prefix="mia_", hex_length=48)
            or not _opaque_id(reservation.investigation_id, prefix="mpi_", hex_length=48)
            or not _hex_digest(reservation.prepared_integrity_digest)
            or not _hex_digest(reservation.authorization_integrity_digest)
            or not _opaque_id(reservation.source_plan_id, prefix="mrp_", hex_length=48)
            or type(reservation.source_plan_version) is not int
            or reservation.source_plan_version < 1
            or not _hex_digest(reservation.source_plan_integrity_digest)
            or not _opaque_id(reservation.source_intent_id, prefix="mmri_", hex_length=48)
            or not _hex_digest(reservation.source_intent_digest)
            or not _hex_digest(reservation.source_evidence_digest)
            or type(reservation.total_node_count) is not int
            or type(reservation.leaf_question_count) is not int
            or not 1 <= reservation.leaf_question_count <= reservation.total_node_count <= _MAX_NODES
            or reservation.route_policy not in {"cheapest", "balanced", "highest_quality"}
            or any(type(value) is not str or not value or len(value) > 256 for value in text_fields)
            or not _hex_digest(reservation.dispatch_config_digest)
            or not _hex_digest(reservation.pricing_digest)
            or not _hex_digest(reservation.workload_digest)
            or type(reservation.quoted_ceiling_cents) is not int
            or type(reservation.approved_ceiling_cents) is not int
            or type(reservation.reserved_cents) is not int
            or not 0 < reservation.quoted_ceiling_cents <= reservation.approved_ceiling_cents
            or reservation.reserved_cents != reservation.approved_ceiling_cents
            or reservation.approved_ceiling_cents > _MAX_CENTS
            or not _hex_digest(reservation.launch_manifest_digest)
            or not _hex_digest(reservation.request_digest)
            or not _opaque_id(reservation.spend_run_id, prefix="mlsr_", hex_length=48)
            or not _opaque_id(reservation.session_id, prefix="mls_", hex_length=48)
            or not _timestamp(reservation.reserved_at)
            or reservation.state != "launch_reserved"
            or reservation.execution_started is not False
            or reservation.background_work_authorized is not False
            or any(value is not None for value in (
                reservation.event_authority_digest, reservation.graph_authority_digest,
                reservation.provider_authority_digest, reservation.task_authority_digest,
            ))):
        raise ValueError("launch reservation integrity conflicts")


def _derived_id(domain: str, prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(_canonical({"domain": domain, "parts": parts}).encode()).hexdigest()
    return prefix + digest[:48]


def _new_node_id() -> str:
    return "mrpn_" + secrets.token_hex(24)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "InvestigationActivationAuthorization", "InvestigationActivationQuote",
    "InvestigationLaunchReservation", "PreparedInvestigation",
    "ResearchPlan", "ResearchPlanError", "ResearchPlanLedger", "ResearchPlanStorageError",
    "ResearchPlanTooLargeError", "ResearchPlanUnavailableError", "ResearchPlanValidationError",
]
