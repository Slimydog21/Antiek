"""The 30/70 platform/IP-holder split and the 70% creator payout ratio.

Pure-functional; no I/O. Cent-precise via Decimal."""

from __future__ import annotations

from decimal import Decimal


PLATFORM_CUT = Decimal("0.30")  # per master-spec §9.0.1
IP_HOLDER_CUT = Decimal("0.70")
CREATOR_PAYOUT_RATIO = Decimal("0.70")  # per §13.9 — of the IP-holder share


def split_platform_vs_ip(total_cents: int) -> tuple[int, int]:
    """Return (platform_cents, ip_holder_pool_cents). Sums to total."""
    if total_cents <= 0:
        return (0, 0)
    ip_pool = int(Decimal(total_cents) * IP_HOLDER_CUT)
    platform = total_cents - ip_pool
    return (platform, ip_pool)


def apply_creator_ratio(ip_holder_pool_cents: int) -> tuple[int, int]:
    """Within the IP-holder share, the creator-share is 70% (§13.9).

    Returns (creator_pool_cents, publisher_pool_cents). When publishers
    have not opted in, the publisher_pool stays in escrow per §9.10.
    """
    if ip_holder_pool_cents <= 0:
        return (0, 0)
    creator = int(Decimal(ip_holder_pool_cents) * CREATOR_PAYOUT_RATIO)
    publisher = ip_holder_pool_cents - creator
    return (creator, publisher)
