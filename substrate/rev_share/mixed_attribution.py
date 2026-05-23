"""Mixed creator + publisher proportional split (Sprint 25+).

Per master-spec §9.6 + the Sprint 25+ rev-share phase: when a session
pulls from both a publisher's licensed content AND a creator's public
note, the 70% IP-holder pool must split proportionally to the
attribution shares, never duplicating dollars.

The contract: every document carries a (kind, recipient_ref) tuple
in document_to_recipient. The function distributes the IP-holder
pool by share, then aggregates per (kind, recipient_ref) so a single
publisher referenced via multiple documents gets one line item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class MixedAttributionInput:
    """One impression's mixed-attribution input."""

    impression_id: str
    ip_holder_pool_cents: int
    attribution_shares: dict[str, float]  # document_id → share in [0, 1]
    document_to_recipient: dict[str, tuple[str, str]]  # doc_id → (kind, ref)


@dataclass(frozen=True)
class MixedAttributionLine:
    """One aggregated line in the result."""

    kind: str  # "creator" | "publisher"
    recipient_ref: str
    amount_cents: int
    contributing_doc_ids: tuple[str, ...]


@dataclass(frozen=True)
class MixedAttributionResult:
    """The full split result."""

    impression_id: str
    lines: tuple[MixedAttributionLine, ...]
    unallocated_cents: int  # cents that fell off due to rounding


def split_mixed_attribution(
    inp: MixedAttributionInput,
) -> MixedAttributionResult:
    """Split the IP-holder pool by share, aggregating per recipient.

    Rounding policy: per-document share is floor-cents; any residual
    from rounding stays in unallocated_cents — never doubled, never
    overpaid. Caller (the operator-only audit dashboard) reconciles
    unallocated_cents into the platform residual ledger.
    """
    if inp.ip_holder_pool_cents <= 0:
        return MixedAttributionResult(
            impression_id=inp.impression_id,
            lines=(),
            unallocated_cents=0,
        )

    per_recipient_cents: dict[tuple[str, str], int] = {}
    per_recipient_docs: dict[tuple[str, str], list[str]] = {}
    allocated = 0
    for doc_id, share in inp.attribution_shares.items():
        if doc_id not in inp.document_to_recipient:
            continue
        kind, recipient_ref = inp.document_to_recipient[doc_id]
        cents = int(inp.ip_holder_pool_cents * share)
        if cents <= 0:
            continue
        key = (kind, recipient_ref)
        per_recipient_cents[key] = per_recipient_cents.get(key, 0) + cents
        per_recipient_docs.setdefault(key, []).append(doc_id)
        allocated += cents

    lines = tuple(
        MixedAttributionLine(
            kind=kind,
            recipient_ref=ref,
            amount_cents=per_recipient_cents[(kind, ref)],
            contributing_doc_ids=tuple(sorted(per_recipient_docs[(kind, ref)])),
        )
        for (kind, ref) in sorted(per_recipient_cents.keys())
    )
    unallocated = inp.ip_holder_pool_cents - allocated
    return MixedAttributionResult(
        impression_id=inp.impression_id,
        lines=lines,
        unallocated_cents=max(0, unallocated),
    )
