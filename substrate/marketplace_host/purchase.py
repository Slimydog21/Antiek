"""Purchase receipt adapter — manual first (SPR-03).

No card numbers, no Stripe. A receipt is an opaque reference the operator
pastes as proof of a purchase already completed outside the system.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .library import HostStore


@dataclass(frozen=True)
class PurchaseReceipt:
    receipt_id: str
    book_id: str
    owner_id: str
    opaque_reference: str
    note: str = ""


@runtime_checkable
class PurchaseAdapter(Protocol):
    def record_receipt(
        self,
        *,
        book_id: str,
        owner_id: str,
        opaque_reference: str,
        note: str = "",
    ) -> PurchaseReceipt: ...


@dataclass
class ManualPurchaseReceipt:
    """Default adapter: store an opaque proof string; never store card data."""

    store: HostStore

    def record_receipt(
        self,
        *,
        book_id: str,
        owner_id: str,
        opaque_reference: str,
        note: str = "",
    ) -> PurchaseReceipt:
        if not book_id.strip():
            raise ValueError("book_id is required")
        if not owner_id.strip():
            raise ValueError("owner_id is required")
        ref = (opaque_reference or "").strip()
        if not ref:
            raise ValueError("opaque_reference is required")
        # Refuse obvious card-like payloads (long digit runs).
        digits = "".join(c for c in ref if c.isdigit())
        if len(digits) >= 13 and digits == ref.replace(" ", "").replace("-", ""):
            raise ValueError(
                "opaque_reference looks like a card number; store only a "
                "merchant order id or receipt token"
            )
        rid = "rcpt_" + hashlib.sha256(
            f"{owner_id}:{book_id}:{ref}".encode()
        ).hexdigest()[:16]
        receipt = PurchaseReceipt(
            receipt_id=rid,
            book_id=book_id.strip(),
            owner_id=owner_id.strip(),
            opaque_reference=ref,
            note=(note or "").strip(),
        )
        self.store.put_receipt(
            rid,
            {
                "receipt_id": receipt.receipt_id,
                "book_id": receipt.book_id,
                "owner_id": receipt.owner_id,
                "opaque_reference": receipt.opaque_reference,
                "note": receipt.note,
            },
        )
        return receipt


def new_manual_receipt_id() -> str:
    return f"rcpt_{uuid.uuid4().hex[:16]}"
