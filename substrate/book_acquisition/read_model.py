"""Verified, operator-scoped recovery view for book acquisition lifecycles."""

from __future__ import annotations

from dataclasses import dataclass

from .authorization import (
    AcquisitionIntegrityError,
    BookAcquisitionConnection,
    PurchaseAuthorization,
    PurchaseIntent,
    get_purchase_authorization,
    get_purchase_intent,
)
from .port import AuthorizedBookPort, verify_port_receipt


@dataclass(frozen=True)
class BookAcquisitionRecord:
    intent: PurchaseIntent
    authorization: PurchaseAuthorization | None
    port: AuthorizedBookPort | None


@dataclass(frozen=True)
class BookAcquisitionPage:
    records: tuple[BookAcquisitionRecord, ...]
    next_cursor: str | None


def list_book_acquisitions(
    con: BookAcquisitionConnection,
    *,
    operator_id: str,
    signing_key: bytes,
    limit: int = 50,
    after: str | None = None,
) -> BookAcquisitionPage:
    if not isinstance(operator_id, str) or not operator_id.strip():
        raise ValueError("operator_id is required")
    operator_id = operator_id.strip()
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    if after is not None and (not isinstance(after, str) or not after.strip()):
        raise ValueError("after must be a nonempty cursor")

    rows = con.execute(
        "SELECT intent_receipt_id FROM book_purchase_intents "
        "WHERE operator_id = ? AND (? IS NULL OR intent_receipt_id > ?) "
        "ORDER BY intent_receipt_id LIMIT ?",
        [operator_id, after, after, limit + 1],
    ).fetchall()
    page_ids = [str(row[0]) for row in rows[:limit]]
    records = tuple(
        _load_record(
            con,
            intent_receipt_id=intent_id,
            operator_id=operator_id,
            signing_key=signing_key,
        )
        for intent_id in page_ids
    )
    next_cursor = page_ids[-1] if len(rows) > limit and page_ids else None
    return BookAcquisitionPage(records=records, next_cursor=next_cursor)


def _load_record(
    con: BookAcquisitionConnection,
    *,
    intent_receipt_id: str,
    operator_id: str,
    signing_key: bytes,
) -> BookAcquisitionRecord:
    intent = get_purchase_intent(
        con,
        intent_receipt_id=intent_receipt_id,
        signing_key=signing_key,
    )
    if intent.operator_id != operator_id:
        raise AcquisitionIntegrityError("purchase intent operator does not match caller")
    auth_row = con.execute(
        "SELECT authorization_receipt_id FROM book_purchase_authorizations "
        "WHERE intent_receipt_id = ?",
        [intent.intent_receipt_id],
    ).fetchone()
    if auth_row is None:
        if intent.status != "needs_operator_authorization":
            raise AcquisitionIntegrityError("terminal purchase intent has no authorization receipt")
        return BookAcquisitionRecord(intent=intent, authorization=None, port=None)

    authorization = get_purchase_authorization(
        con,
        authorization_receipt_id=str(auth_row[0]),
        expected_operator_id=operator_id,
        signing_key=signing_key,
    )
    if authorization.intent_receipt_id != intent.intent_receipt_id:
        raise AcquisitionIntegrityError("authorization links to another purchase intent")
    port_row = con.execute(
        "SELECT port_receipt_id FROM book_authorized_ports WHERE authorization_receipt_id = ?",
        [authorization.authorization_receipt_id],
    ).fetchone()
    if port_row is None:
        return BookAcquisitionRecord(intent=intent, authorization=authorization, port=None)
    if authorization.decision.value != "authorized":
        raise AcquisitionIntegrityError("denied authorization has a port receipt")
    port = verify_port_receipt(
        con,
        port_receipt_id=str(port_row[0]),
        authorization_receipt_id=authorization.authorization_receipt_id,
        operator_id=operator_id,
        signing_key=signing_key,
    )
    return BookAcquisitionRecord(intent=intent, authorization=authorization, port=port)


__all__ = [
    "BookAcquisitionPage",
    "BookAcquisitionRecord",
    "list_book_acquisitions",
]
