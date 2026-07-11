"""Pure list-price estimates for web-layer calls."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Literal

Vendor = Literal["exa", "jina", "swap_stub"]
Operation = Literal["search", "find_similar", "extract"]


@dataclass(frozen=True, slots=True)
class CostRecord:
    vendor: Vendor
    operation: Operation
    units: int
    usd_estimate: Decimal


# Exa search: $7 / 1,000 requests. Source: https://exa.ai/pricing
# and docs/integration_exa_browserbase.md; verified 2026-07-11.
_EXA_SEARCH_PER_CALL = Decimal("0.007")
# Exa findSimilar: $1 / 1,000 calls. Same source; explicitly marked there as
# absent from the public price page. Snapshot re-read 2026-07-11.
_EXA_SIMILAR_PER_CALL = Decimal("0.001")
# Jina Reader basic no-key use: $0 per URL. Source:
# https://jina.ai/en-US/reader/ FAQ; verified 2026-07-11. Higher-rate keyed
# token billing is deliberately outside this reference adapter's cost row.
_JINA_EXTRACT_PER_URL = Decimal("0.00")
# Swap stub is an in-process test adapter, not a billed service; 2026-07-11.
_SWAP_STUB_PER_URL = Decimal("0.00")

_UNIT_PRICES: Final = MappingProxyType(
    {
        ("exa", "search"): _EXA_SEARCH_PER_CALL,
        ("exa", "find_similar"): _EXA_SIMILAR_PER_CALL,
        ("jina", "extract"): _JINA_EXTRACT_PER_URL,
        ("swap_stub", "extract"): _SWAP_STUB_PER_URL,
    }
)


def estimate_cost(vendor: Vendor, operation: Operation, units: int) -> CostRecord:
    """Return deterministic list-price cost; no clock, I/O, or rounding occurs."""

    if units < 0:
        raise ValueError("units must be non-negative")
    try:
        unit_price = _UNIT_PRICES[(vendor, operation)]
    except KeyError as error:
        raise ValueError(f"unsupported vendor operation: {vendor}/{operation}") from error
    return CostRecord(vendor, operation, units, unit_price * units)
