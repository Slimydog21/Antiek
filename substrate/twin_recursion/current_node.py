"""Owner-only current-authority projection for historical canonical twin nodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from runtime.db_lock import LockedConnection

from .evidence_promotion import TwinEvidencePromotionLedger
from .ledger import TwinRecursionLedger
from .promotion_writer import (
    canonical_promotion_node_id,
    canonical_promotion_node_metadata,
)


@dataclass(frozen=True)
class CurrentCanonicalTwinNode:
    node_id: str
    candidate_id: str
    review_id: str
    kind: Literal["insight", "question"]
    text: str
    owner_id: str
    status: Literal["current"] = "current"
    authority: Literal["owner_reviewed_evidence_bound_graph_node_v1"] = (
        "owner_reviewed_evidence_bound_graph_node_v1"
    )


@dataclass(frozen=True)
class HistoricalCanonicalTwinNodeWithheld:
    status: Literal["historical_withheld"] = "historical_withheld"
    authority: Literal["unavailable"] = "unavailable"


CanonicalTwinNodeView = CurrentCanonicalTwinNode | HistoricalCanonicalTwinNodeWithheld


def _exact_text(value: object, field: str) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 512:
        raise ValueError(f"{field} must be an exact bounded non-empty string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field} contains control characters")
    return value


def read_current_canonical_twin_node(
    con: LockedConnection,
    promotions: TwinEvidencePromotionLedger,
    twins: TwinRecursionLedger,
    *,
    owner_id: str,
    candidate_id: str,
) -> CanonicalTwinNodeView:
    """Return one exact current node, or a uniform non-disclosing withheld view."""
    if type(con) is not LockedConnection:
        raise TypeError("current canonical node reader requires the exact locked graph connection")
    if type(promotions) is not TwinEvidencePromotionLedger:
        raise TypeError("current canonical node reader requires the exact promotion ledger")
    if type(twins) is not TwinRecursionLedger:
        raise TypeError("current canonical node reader requires the exact twin ledger")
    owner_id = _exact_text(owner_id, "owner_id")
    candidate_id = _exact_text(candidate_id, "candidate_id")
    withheld = HistoricalCanonicalTwinNodeWithheld()
    try:
        with promotions.accepted_snapshot(
            con, twins, owner_id=owner_id, candidate_id=candidate_id
        ) as snapshot:
            authority = snapshot.authority
            candidate = authority.candidate
            node_id = canonical_promotion_node_id(authority)
            rows = con.execute(
                "SELECT canonical_label,node_type,embedding,graph_scope,metadata,"
                "owner_user_id FROM nodes WHERE node_id=? AND owner_user_id=?",
                [node_id, owner_id],
            ).fetchall()
            if len(rows) != 1:
                return withheld
            row = rows[0]
            metadata = json.loads(row[4])
            expected = (
                candidate.text,
                candidate.kind,
                None,
                "depth",
                canonical_promotion_node_metadata(authority),
                owner_id,
            )
            if (*row[:4], metadata, *row[5:]) != expected:
                return withheld
            promotions.require_snapshot_current(snapshot)
            return CurrentCanonicalTwinNode(
                node_id=node_id,
                candidate_id=candidate.candidate_id,
                review_id=authority.review.review_id,
                kind=candidate.kind,
                text=candidate.text,
                owner_id=candidate.owner_id,
            )
    except Exception:
        return withheld


__all__ = [
    "CanonicalTwinNodeView",
    "CurrentCanonicalTwinNode",
    "HistoricalCanonicalTwinNodeWithheld",
    "read_current_canonical_twin_node",
]
