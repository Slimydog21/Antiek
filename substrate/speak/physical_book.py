"""Speak SPR-09 — physical-book ordering hook (provider-agnostic).

The operator wants paperbacks/hardcovers. This ships the ECONOMICS + a
provider-agnostic ordering hook over the existing pdf/epub export — NOT
fulfillment. There is no print-on-demand vendor anywhere in the
codebase, and importing/using this module does NOT print or mail a
book: an order is QUOTED and shaped, never fulfilled. The live vendor +
shipping + payment integration is a named, deferred downstream (a
ResearchRunner-style provider swap).

Cost allocation per the matrix (M5):
  • public            → the algorithmic-split economics persist (the 70%
                         covers/credits the physical work) → payer 'split';
  • private-never-published → the creator carries the physical cost
                         → payer 'creator'.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Protocol, runtime_checkable

from . import economics_mode
from .events import SPEAK_BOOK_ORDER_QUOTED, record_speak_event
from .ids import new_order_id
from .schema import ensure_speak_schema

_FORMATS = frozenset({"paperback", "hardcover"})


@runtime_checkable
class PhysicalBookProvider(Protocol):
    """A POD vendor seam. The eventual Lulu / IngramSpark adapter
    satisfies this; ``StubPhysicalBookProvider`` is the only
    implementation today and prints nothing."""

    name: str

    def quote(self, *, book_format: str, page_count: int) -> Decimal:
        ...


class StubPhysicalBookProvider:
    """The only provider today. Quotes a plausible unit cost so the
    economics can be exercised — and fulfils NOTHING. A vendor adapter
    drops in here later without touching call sites."""

    name = "stub"

    _BASE = {"paperback": Decimal("8.00"), "hardcover": Decimal("18.00")}
    _PER_PAGE = Decimal("0.02")

    def quote(self, *, book_format: str, page_count: int) -> Decimal:
        if book_format not in _FORMATS:
            raise ValueError(f"unknown book_format: {book_format!r}")
        return (self._BASE[book_format] + self._PER_PAGE * Decimal(page_count)).quantize(
            Decimal("0.01")
        )


@dataclass(frozen=True)
class BookOrderQuote:
    order_id: str
    project_id: str
    book_format: str
    provider: str
    cost_usd: Decimal
    payer: str  # 'creator' | 'split'
    fulfilled: bool = False  # always False — quote only, no live vendor


def order_physical_book(
    con: Any,
    *,
    project_id: str,
    book_format: str,
    page_count: int,
    publication_id: Optional[str] = None,
    provider: Optional[PhysicalBookProvider] = None,
) -> BookOrderQuote:
    """Shape + cost-quote a physical-book order against the provider
    interface. Allocates the payer per the matrix. Records a 'quoted'
    order — never fulfilled (no live vendor)."""
    ensure_speak_schema(con)
    if book_format not in _FORMATS:
        raise ValueError(f"unknown book_format: {book_format!r}")
    provider = provider or StubPhysicalBookProvider()

    policy = economics_mode.policy_for_project(con, project_id)
    # Public → split economics persist; private-never-published → creator.
    payer = "creator" if policy.creator_carries_cost else "split"
    cost = provider.quote(book_format=book_format, page_count=page_count)

    order_id = new_order_id()
    con.execute(
        "INSERT INTO speak_book_orders "
        "(order_id, publication_id, project_id, book_format, provider, payer, "
        " cost_usd, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'quoted')",
        [order_id, publication_id, project_id, book_format, provider.name, payer, cost],
    )
    record_speak_event(
        SPEAK_BOOK_ORDER_QUOTED,
        {"order_id": order_id, "book_format": book_format, "provider": provider.name,
         "payer": payer, "cost_usd": str(cost), "fulfilled": False},
        project_id=project_id,
    )
    return BookOrderQuote(
        order_id=order_id, project_id=project_id, book_format=book_format,
        provider=provider.name, cost_usd=cost, payer=payer, fulfilled=False,
    )
