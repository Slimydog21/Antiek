"""Current owner-only normalized citations for reviewed canonical twin nodes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Union

from runtime.db_lock import LockedConnection

from .current_node import (
    CurrentCanonicalTwinNode,
    HistoricalCanonicalTwinNodeWithheld,
    _current_node_for_authority,
    _exact_text,
)
from .evidence_promotion import AcceptedTwinPromotionAuthority, TwinEvidencePromotionLedger
from .ledger import TwinRecursionLedger
from .promotion_writer import (
    _CITATION_COLUMNS,
    CanonicalTwinNodeCitation,
    canonical_promotion_node_citations,
)


@dataclass(frozen=True)
class CurrentCanonicalTwinNodeCitations:
    node: CurrentCanonicalTwinNode
    citations: tuple[CanonicalTwinNodeCitation, ...]
    status: Literal["current"] = "current"
    authority: Literal["owner_reviewed_evidence_bound_node_citations_v1"] = (
        "owner_reviewed_evidence_bound_node_citations_v1"
    )


CanonicalTwinNodeCitationsView = Union[  # noqa: UP007 - Python 3.11 type-alias support.
    CurrentCanonicalTwinNodeCitations, HistoricalCanonicalTwinNodeWithheld
]


def read_current_canonical_twin_node_citations(
    con: LockedConnection,
    promotions: TwinEvidencePromotionLedger,
    twins: TwinRecursionLedger,
    *,
    owner_id: str,
    candidate_id: str,
) -> CanonicalTwinNodeCitationsView:
    """Return exact current citations, or the same uniform historical denial."""
    if type(con) is not LockedConnection:
        raise TypeError("current citation reader requires the exact locked graph connection")
    if type(promotions) is not TwinEvidencePromotionLedger:
        raise TypeError("current citation reader requires the exact promotion ledger")
    if type(twins) is not TwinRecursionLedger:
        raise TypeError("current citation reader requires the exact twin ledger")
    owner_id = _exact_text(owner_id, "owner_id")
    candidate_id = _exact_text(candidate_id, "candidate_id")
    withheld = HistoricalCanonicalTwinNodeWithheld()
    try:
        with promotions.accepted_snapshot(
            con, twins, owner_id=owner_id, candidate_id=candidate_id
        ) as snapshot:
            node = _current_node_for_authority(con, snapshot.authority, owner_id=owner_id)
            if node is None:
                return withheld
            expected = canonical_promotion_node_citations(snapshot.authority)
            rows = con.execute(
                f"SELECT {_CITATION_COLUMNS} FROM canonical_twin_node_citations "
                "WHERE node_id=? AND owner_id=? ORDER BY ordinal",
                [node.node_id, owner_id],
            ).fetchall()
            if rows != [tuple(asdict(citation).values()) for citation in expected]:
                return withheld
            promotions.require_snapshot_current(snapshot)
            return CurrentCanonicalTwinNodeCitations(node=node, citations=expected)
    except Exception:
        return withheld


def current_canonical_twin_node_citations_for_authority(
    con: LockedConnection,
    authority: AcceptedTwinPromotionAuthority,
    *,
    owner_id: str,
) -> CurrentCanonicalTwinNodeCitations | None:
    """Project one already verified authority without reopening its ledger."""
    if type(con) is not LockedConnection:
        raise TypeError("current citation projection requires the exact locked connection")
    if type(authority) is not AcceptedTwinPromotionAuthority:
        raise TypeError("current citation projection requires exact accepted authority")
    owner_id = _exact_text(owner_id, "owner_id")
    node = _current_node_for_authority(con, authority, owner_id=owner_id)
    if node is None:
        return None
    expected = canonical_promotion_node_citations(authority)
    rows = con.execute(
        f"SELECT {_CITATION_COLUMNS} FROM canonical_twin_node_citations "
        "WHERE node_id=? AND owner_id=? ORDER BY ordinal",
        [node.node_id, owner_id],
    ).fetchall()
    if rows != [tuple(asdict(citation).values()) for citation in expected]:
        return None
    return CurrentCanonicalTwinNodeCitations(node=node, citations=expected)


__all__ = [
    "CanonicalTwinNodeCitationsView",
    "CurrentCanonicalTwinNodeCitations",
    "current_canonical_twin_node_citations_for_authority",
    "read_current_canonical_twin_node_citations",
]
