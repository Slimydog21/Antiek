"""Durable, spend-inert receipts for operator-approved book acquisition."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from runtime.db_lock import LockedConnection


class BookAcquisitionConnection(Protocol):
    """Minimal query surface shared by locked writers and read-only connections."""

    def execute(self, query: str, *args: Any, **kwargs: Any) -> Any: ...


class AcquisitionIntegrityError(RuntimeError):
    """Stored acquisition state does not match its signed contract."""


class AcquisitionConflictError(RuntimeError):
    """A replay conflicts with an existing terminal decision."""


class DesiredFormat(StrEnum):
    EPUB = "epub"


class AuthorizationDecision(StrEnum):
    AUTHORIZED = "authorized"
    DENIED = "denied"


@dataclass(frozen=True)
class PurchaseIntent:
    intent_receipt_id: str
    operator_id: str
    title: str
    author: str
    store: str
    max_price_usd_cents: int
    desired_format: DesiredFormat
    intent_hash: str
    status: str


@dataclass(frozen=True)
class PurchaseAuthorization:
    authorization_receipt_id: str
    intent_receipt_id: str
    intent_hash: str
    operator_id: str
    decision: AuthorizationDecision
    authorized_price_ceiling_usd_cents: int
    authorization_hash: str

    @property
    def purchase_occurred(self) -> bool:
        return False


_INTENT_DDL = """
CREATE TABLE IF NOT EXISTS book_purchase_intents (
    intent_receipt_id TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    store TEXT NOT NULL,
    max_price_usd_cents BIGINT NOT NULL CHECK (max_price_usd_cents >= 0),
    desired_format TEXT NOT NULL CHECK (desired_format = 'epub'),
    intent_hash TEXT NOT NULL UNIQUE
    ,status TEXT NOT NULL CHECK (
        status IN ('needs_operator_authorization', 'authorized', 'denied')
    )
    ,intent_mac TEXT NOT NULL
)
"""

_AUTH_DDL = """
CREATE TABLE IF NOT EXISTS book_purchase_authorizations (
    authorization_receipt_id TEXT PRIMARY KEY,
    intent_receipt_id TEXT NOT NULL UNIQUE
        REFERENCES book_purchase_intents(intent_receipt_id),
    intent_hash TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('authorized', 'denied')),
    authorized_price_ceiling_usd_cents BIGINT NOT NULL
        CHECK (authorized_price_ceiling_usd_cents >= 0),
    authorization_hash TEXT NOT NULL UNIQUE
    ,authorization_mac TEXT NOT NULL
)
"""


def _require_writer(con: LockedConnection) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError("book acquisition writes require LockedConnection")


def _text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized) > 512:
        raise ValueError(f"{field} exceeds 512 characters")
    return normalized


def _cents(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _canonical(values: Mapping[str, object]) -> str:
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _key(signing_key: bytes) -> bytes:
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")
    return signing_key


def _mac(signing_key: bytes, payload: str) -> str:
    return hmac.new(_key(signing_key), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def ensure_schema(con: LockedConnection) -> None:
    _require_writer(con)
    con.execute(_INTENT_DDL)
    con.execute(_AUTH_DDL)


def _intent_payload(
    *,
    operator_id: str,
    title: str,
    author: str,
    store: str,
    max_price_usd_cents: int,
    desired_format: DesiredFormat,
) -> dict[str, object]:
    return {
        "author": author,
        "desired_format": desired_format.value,
        "max_price_usd_cents": max_price_usd_cents,
        "operator_id": operator_id,
        "store": store,
        "title": title,
    }


def create_purchase_intent(
    con: LockedConnection,
    *,
    operator_id: str,
    title: str,
    author: str,
    store: str,
    max_price_usd_cents: int,
    signing_key: bytes,
    desired_format: DesiredFormat = DesiredFormat.EPUB,
) -> PurchaseIntent:
    _require_writer(con)
    operator_id = _text(operator_id, "operator_id")
    title = _text(title, "title")
    author = _text(author, "author")
    store = _text(store, "store")
    max_price_usd_cents = _cents(max_price_usd_cents, "max_price_usd_cents")
    if not isinstance(desired_format, DesiredFormat):
        raise ValueError("desired_format must be DesiredFormat.EPUB")
    payload = _intent_payload(
        operator_id=operator_id,
        title=title,
        author=author,
        store=store,
        max_price_usd_cents=max_price_usd_cents,
        desired_format=desired_format,
    )
    intent_hash = _sha(_canonical(payload))
    intent_mac = _mac(signing_key, _canonical(payload))
    receipt_id = f"bookintent-{intent_hash}"
    existing = con.execute(
        "SELECT operator_id, title, author, store, max_price_usd_cents, "
        "desired_format, intent_hash, status, intent_mac FROM book_purchase_intents "
        "WHERE intent_receipt_id = ?",
        [receipt_id],
    ).fetchone()
    immutable = (
        operator_id,
        title,
        author,
        store,
        max_price_usd_cents,
        desired_format.value,
        intent_hash,
    )
    if existing is not None:
        if tuple(existing[:7]) != immutable or not hmac.compare_digest(
            str(existing[8]), intent_mac
        ):
            raise AcquisitionConflictError("intent receipt replay conflicts with stored state")
        return PurchaseIntent(
            receipt_id, *immutable[:5], desired_format, intent_hash, str(existing[7])
        )
    con.execute(
        "INSERT INTO book_purchase_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [receipt_id, *immutable, "needs_operator_authorization", intent_mac],
    )
    return PurchaseIntent(
        receipt_id,
        *immutable[:5],
        desired_format,
        intent_hash,
        "needs_operator_authorization",
    )


def _load_verified_intent(
    con: BookAcquisitionConnection, intent_receipt_id: str, signing_key: bytes
) -> PurchaseIntent:
    receipt_id = _text(intent_receipt_id, "intent_receipt_id")
    row = con.execute(
        "SELECT operator_id, title, author, store, max_price_usd_cents, "
        "desired_format, intent_hash, status, intent_mac FROM book_purchase_intents "
        "WHERE intent_receipt_id = ?",
        [receipt_id],
    ).fetchone()
    if row is None:
        raise AcquisitionIntegrityError("purchase intent receipt does not exist")
    operator_id, title, author, store, cents, format_value, stored_hash, status, stored_mac = row
    try:
        desired_format = DesiredFormat(str(format_value))
    except ValueError as exc:
        raise AcquisitionIntegrityError("purchase intent format is invalid") from exc
    payload = _intent_payload(
        operator_id=str(operator_id),
        title=str(title),
        author=str(author),
        store=str(store),
        max_price_usd_cents=int(cents),
        desired_format=desired_format,
    )
    computed_hash = _sha(_canonical(payload))
    computed_mac = _mac(signing_key, _canonical(payload))
    if stored_hash != computed_hash or receipt_id != f"bookintent-{computed_hash}":
        raise AcquisitionIntegrityError("purchase intent receipt is tampered")
    if not hmac.compare_digest(str(stored_mac), computed_mac):
        raise AcquisitionIntegrityError("purchase intent signature is invalid")
    return PurchaseIntent(
        receipt_id,
        str(operator_id),
        str(title),
        str(author),
        str(store),
        int(cents),
        desired_format,
        computed_hash,
        str(status),
    )


def get_purchase_intent(
    con: BookAcquisitionConnection,
    *,
    intent_receipt_id: str,
    signing_key: bytes,
) -> PurchaseIntent:
    """Load and authenticate one persisted purchase intent."""
    return _load_verified_intent(con, intent_receipt_id, signing_key)


def authorize_purchase_intent(
    con: LockedConnection,
    *,
    intent_receipt_id: str,
    operator_id: str,
    decision: AuthorizationDecision,
    authorized_price_ceiling_usd_cents: int,
    signing_key: bytes,
) -> PurchaseAuthorization:
    _require_writer(con)
    intent = _load_verified_intent(con, intent_receipt_id, signing_key)
    operator_id = _text(operator_id, "operator_id")
    cents = _cents(
        authorized_price_ceiling_usd_cents,
        "authorized_price_ceiling_usd_cents",
    )
    if not isinstance(decision, AuthorizationDecision):
        raise ValueError("decision must be an AuthorizationDecision")
    if operator_id != intent.operator_id:
        raise AcquisitionIntegrityError("operator does not own purchase intent")
    if cents > intent.max_price_usd_cents:
        raise AcquisitionIntegrityError("authorization exceeds purchase intent ceiling")
    if decision is AuthorizationDecision.DENIED and cents != 0:
        raise ValueError("denied authorization must have a zero ceiling")
    payload = {
        "authorized_price_ceiling_usd_cents": cents,
        "decision": decision.value,
        "intent_hash": intent.intent_hash,
        "intent_receipt_id": intent.intent_receipt_id,
        "operator_id": operator_id,
        "purchase_occurred": False,
    }
    authorization_hash = _sha(_canonical(payload))
    authorization_mac = _mac(signing_key, _canonical(payload))
    receipt_id = f"bookauth-{authorization_hash}"
    existing = con.execute(
        "SELECT authorization_receipt_id, intent_hash, operator_id, decision, "
        "authorized_price_ceiling_usd_cents, authorization_hash, authorization_mac "
        "FROM book_purchase_authorizations WHERE intent_receipt_id = ?",
        [intent.intent_receipt_id],
    ).fetchone()
    expected = (
        receipt_id,
        intent.intent_hash,
        operator_id,
        decision.value,
        cents,
        authorization_hash,
        authorization_mac,
    )
    if existing is not None:
        if tuple(existing) != expected:
            raise AcquisitionConflictError("purchase intent already has another decision")
        if intent.status != decision.value:
            raise AcquisitionIntegrityError(
                "purchase intent status does not match terminal receipt"
            )
    else:
        if intent.status != "needs_operator_authorization":
            raise AcquisitionIntegrityError("terminal purchase intent has no authorization receipt")
        terminal_status = decision.value
        try:
            con.execute("BEGIN TRANSACTION")
            con.execute(
                "UPDATE book_purchase_intents SET status = ? "
                "WHERE intent_receipt_id = ? AND status = 'needs_operator_authorization'",
                [terminal_status, intent.intent_receipt_id],
            )
            status_row = con.execute(
                "SELECT status FROM book_purchase_intents WHERE intent_receipt_id = ?",
                [intent.intent_receipt_id],
            ).fetchone()
            if status_row != (terminal_status,):
                raise AcquisitionConflictError("purchase intent is already terminal")
            con.execute(
                "INSERT INTO book_purchase_authorizations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [receipt_id, intent.intent_receipt_id, *expected[1:]],
            )
            con.execute("COMMIT")
        except Exception:
            with suppress(Exception):
                con.execute("ROLLBACK")
            raise
    return PurchaseAuthorization(
        receipt_id,
        intent.intent_receipt_id,
        intent.intent_hash,
        operator_id,
        decision,
        cents,
        authorization_hash,
    )


def verify_authorization(
    con: BookAcquisitionConnection,
    *,
    authorization_receipt_id: str,
    expected_operator_id: str,
    signing_key: bytes,
) -> PurchaseAuthorization:
    authorization = get_purchase_authorization(
        con,
        authorization_receipt_id=authorization_receipt_id,
        expected_operator_id=expected_operator_id,
        signing_key=signing_key,
    )
    if authorization.decision is not AuthorizationDecision.AUTHORIZED:
        raise AcquisitionIntegrityError("purchase intent was not authorized")
    return authorization


def get_purchase_authorization(
    con: BookAcquisitionConnection,
    *,
    authorization_receipt_id: str,
    expected_operator_id: str,
    signing_key: bytes,
) -> PurchaseAuthorization:
    """Load and authenticate an authorized or denied lifecycle receipt."""
    receipt_id = _text(authorization_receipt_id, "authorization_receipt_id")
    expected_operator_id = _text(expected_operator_id, "expected_operator_id")
    row = con.execute(
        "SELECT intent_receipt_id, intent_hash, operator_id, decision, "
        "authorized_price_ceiling_usd_cents, authorization_hash, authorization_mac "
        "FROM book_purchase_authorizations WHERE authorization_receipt_id = ?",
        [receipt_id],
    ).fetchone()
    if row is None:
        raise AcquisitionIntegrityError("authorization receipt does not exist")
    intent_id, intent_hash, operator_id, decision_value, cents, stored_hash, stored_mac = row
    intent = _load_verified_intent(con, str(intent_id), signing_key)
    if intent_hash != intent.intent_hash or operator_id != intent.operator_id:
        raise AcquisitionIntegrityError("authorization predecessor binding is invalid")
    if operator_id != expected_operator_id:
        raise AcquisitionIntegrityError("authorization operator does not match caller")
    try:
        decision = AuthorizationDecision(str(decision_value))
    except ValueError as exc:
        raise AcquisitionIntegrityError("authorization decision is invalid") from exc
    payload = {
        "authorized_price_ceiling_usd_cents": int(cents),
        "decision": decision.value,
        "intent_hash": intent.intent_hash,
        "intent_receipt_id": intent.intent_receipt_id,
        "operator_id": str(operator_id),
        "purchase_occurred": False,
    }
    computed_hash = _sha(_canonical(payload))
    computed_mac = _mac(signing_key, _canonical(payload))
    if stored_hash != computed_hash or receipt_id != f"bookauth-{computed_hash}":
        raise AcquisitionIntegrityError("authorization receipt is tampered")
    if not hmac.compare_digest(str(stored_mac), computed_mac):
        raise AcquisitionIntegrityError("authorization signature is invalid")
    if int(cents) > intent.max_price_usd_cents:
        raise AcquisitionIntegrityError("authorization exceeds purchase intent ceiling")
    if decision is AuthorizationDecision.DENIED and int(cents) != 0:
        raise AcquisitionIntegrityError("denied authorization has a nonzero ceiling")
    if intent.status != decision.value:
        raise AcquisitionIntegrityError("purchase intent status does not match authorization")
    return PurchaseAuthorization(
        receipt_id,
        intent.intent_receipt_id,
        intent.intent_hash,
        str(operator_id),
        decision,
        int(cents),
        computed_hash,
    )
