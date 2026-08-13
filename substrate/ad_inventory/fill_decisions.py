"""Durable, idempotent decisions for multi-edge ad-border fills.

A fill is a rendering decision, not a settlement receipt.  The ledger stores
the exact server-selected creative/house payload for a window so retries and
concurrent renders cannot silently select different inventory.  Revenue stays
zero while pricing is unpriced; CPM metadata is ranking input, not proof that
an advertiser was billed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class FillDecisionConflictError(Exception):
    """The owner/window namespace already has a different decision."""


@dataclass(frozen=True)
class FillDecision:
    decision_id: str
    owner_user_id: str
    window_id: str
    document_id: str | None
    page_index: int | None
    lens: str
    positions: tuple[str, ...]
    fills: tuple[dict[str, Any], ...]
    revenue_usd_cents: int
    price_status: str
    replayed: bool


def ensure_table(con: Any) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ad_fill_decisions (
            decision_id          TEXT PRIMARY KEY,
            request_fingerprint  TEXT NOT NULL UNIQUE,
            owner_user_id        TEXT NOT NULL,
            window_id            TEXT NOT NULL,
            document_id          TEXT,
            page_index           INTEGER CHECK (page_index IS NULL OR page_index >= 0),
            lens                 TEXT NOT NULL,
            positions_json       TEXT NOT NULL,
            fills_json           TEXT NOT NULL,
            revenue_usd_cents    INTEGER NOT NULL
                CHECK (revenue_usd_cents >= 0),
            price_status         TEXT NOT NULL
                CHECK (price_status IN ('unpriced', 'settled')),
            decided_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ad_fill_decisions_owner_window
        ON ad_fill_decisions(owner_user_id, window_id)
        """
    )
    con.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ad_fill_decisions_owner_window
        ON ad_fill_decisions(owner_user_id, window_id)
        """
    )


def _fingerprint(
    *,
    owner_user_id: str,
    window_id: str,
    document_id: str | None,
    page_index: int | None,
    lens: str,
    positions: Sequence[str],
) -> str:
    canonical = json.dumps(
        {
            "document_id": document_id,
            "lens": lens,
            "owner_user_id": owner_user_id,
            "positions": list(positions),
            "page_index": page_index,
            "window_id": window_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decide_fills(
    con: Any,
    *,
    owner_user_id: str,
    window_id: str,
    document_id: str | None,
    page_index: int | None,
    lens: str,
    positions: Sequence[str],
    select_fills: Callable[[], Sequence[Mapping[str, Any]]],
) -> FillDecision:
    """Return the immutable decision for one exact multi-edge request.

    The caller must hold the process-wide DuckDB writer lock.  Selection runs
    only after proving no decision exists, so an exact retry never re-ranks.
    """
    ensure_table(con)
    ordered_positions = tuple(positions)
    fingerprint = _fingerprint(
        owner_user_id=owner_user_id,
        window_id=window_id,
        document_id=document_id,
        page_index=page_index,
        lens=lens,
        positions=ordered_positions,
    )
    existing = con.execute(
        """
        SELECT decision_id, owner_user_id, window_id, document_id, page_index,
               lens, positions_json, fills_json, revenue_usd_cents, price_status
        FROM ad_fill_decisions WHERE request_fingerprint = ?
        """,
        [fingerprint],
    ).fetchone()
    if existing is not None:
        return _from_row(existing, replayed=True)

    window_decision = con.execute(
        """
        SELECT request_fingerprint FROM ad_fill_decisions
        WHERE owner_user_id = ? AND window_id = ?
        """,
        [owner_user_id, window_id],
    ).fetchone()
    if window_decision is not None:
        raise FillDecisionConflictError(
            "window already has a different fill decision"
        )

    fills = tuple(dict(fill) for fill in select_fills())
    if tuple(str(fill.get("position", "")) for fill in fills) != ordered_positions:
        raise ValueError("fill selector must return exactly one fill per requested edge")

    # There is deliberately no CPM-to-impression-price conversion here.  Until
    # a billing authority supplies a settled price, every fill is unpriced $0.
    revenue_usd_cents = 0
    price_status = "unpriced"
    decision_id = f"fill-{fingerprint[:24]}"
    con.execute(
        """
        INSERT INTO ad_fill_decisions (
            decision_id, request_fingerprint, owner_user_id, window_id,
            document_id, page_index, lens, positions_json, fills_json,
            revenue_usd_cents, price_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            decision_id,
            fingerprint,
            owner_user_id,
            window_id,
            document_id,
            page_index,
            lens,
            json.dumps(ordered_positions, separators=(",", ":")),
            json.dumps(fills, sort_keys=True, separators=(",", ":")),
            revenue_usd_cents,
            price_status,
        ],
    )
    return FillDecision(
        decision_id=decision_id,
        owner_user_id=owner_user_id,
        window_id=window_id,
        document_id=document_id,
        page_index=page_index,
        lens=lens,
        positions=ordered_positions,
        fills=fills,
        revenue_usd_cents=revenue_usd_cents,
        price_status=price_status,
        replayed=False,
    )


def _from_row(row: tuple[Any, ...], *, replayed: bool) -> FillDecision:
    return FillDecision(
        decision_id=str(row[0]),
        owner_user_id=str(row[1]),
        window_id=str(row[2]),
        document_id=str(row[3]) if row[3] is not None else None,
        page_index=int(row[4]) if row[4] is not None else None,
        lens=str(row[5]),
        positions=tuple(json.loads(row[6])),
        fills=tuple(dict(item) for item in json.loads(row[7])),
        revenue_usd_cents=int(row[8]),
        price_status=str(row[9]),
        replayed=replayed,
    )


__all__ = [
    "FillDecision",
    "FillDecisionConflictError",
    "decide_fills",
    "ensure_table",
]
