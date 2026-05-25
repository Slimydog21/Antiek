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

    # NOTE: deliberately NO ``fulfill`` method. A provider that can
    # actually print + ship implements ``fulfill``; the stub can't, so
    # ``physical_book.fulfill`` refuses (see PodVendorUnconfigured). This
    # is the same shape as the TTS/openai_tts stub: the seam exists, the
    # capability is gated until a real vendor lands.


class PodVendorUnconfigured(RuntimeError):
    """Raised on any attempt to actually FULFILL (print + ship) an order
    while no live POD vendor is configured. The spec rejects live POD
    fulfillment for v1 (pick a vendor first); this is the structural
    guarantee that nothing prints/ships before that operator decision."""


# ---------------------------------------------------------------------------
# Provider registry — proves the seam is vendor-AGNOSTIC: a real adapter
# (Lulu / IngramSpark / …) registers by name and orders route to it with
# NO change to order_physical_book. We register the stub; we do NOT ship
# a speculative vendor adapter (the spec says pick the vendor first).
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, PhysicalBookProvider] = {}


def register_provider(provider: PhysicalBookProvider) -> None:
    """Register a POD provider by its ``name``. The drop-in point for a
    future vendor adapter — no call site changes."""
    _PROVIDERS[provider.name] = provider


def get_provider(name: str) -> PhysicalBookProvider:
    if name not in _PROVIDERS:
        raise ValueError(
            f"unknown POD provider {name!r}; registered: {sorted(_PROVIDERS)}"
        )
    return _PROVIDERS[name]


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


# The stub is always registered; a real vendor adds itself via
# register_provider() once the operator picks one.
register_provider(StubPhysicalBookProvider())


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
    provider_name: Optional[str] = None,
) -> BookOrderQuote:
    """Shape + cost-quote a physical-book order against the provider
    interface. Allocates the payer per the matrix. Records a 'quoted'
    order — never fulfilled (no live vendor).

    Provider selection (all routes through the same code — vendor-
    agnostic): an explicit ``provider`` instance wins; else
    ``provider_name`` is looked up in the registry; else the stub."""
    ensure_speak_schema(con)
    if book_format not in _FORMATS:
        raise ValueError(f"unknown book_format: {book_format!r}")
    if provider is None:
        provider = get_provider(provider_name) if provider_name else StubPhysicalBookProvider()

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


def fulfill(con: Any, *, order_id: str) -> None:
    """Attempt to actually PRINT + SHIP a quoted order. Refused
    (``PodVendorUnconfigured``) unless the order's provider implements a
    real ``fulfill`` — which the stub does not, and which no provider
    does today (the spec defers live POD until a vendor is chosen). This
    is the seam a future vendor adapter completes; until then, ordering
    is quote-only and this is the single chokepoint that proves nothing
    ships prematurely."""
    ensure_speak_schema(con)
    row = con.execute(
        "SELECT provider FROM speak_book_orders WHERE order_id = ?", [order_id]
    ).fetchone()
    if row is None:
        raise ValueError(f"book order {order_id!r} not found")
    provider = get_provider(row[0])
    vendor_fulfill = getattr(provider, "fulfill", None)
    if not callable(vendor_fulfill):
        raise PodVendorUnconfigured(
            f"provider {row[0]!r} cannot fulfill orders — no live POD vendor "
            "is configured. Ordering is quote-only until the operator picks a "
            "vendor and a fulfilling adapter is registered (spec: defer live "
            "POD to v2)."
        )
    vendor_fulfill(con, order_id=order_id)  # pragma: no cover — no such provider today
