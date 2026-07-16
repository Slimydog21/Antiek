"""Atomic graph materialization for accepted canonical twin proposals."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, dataclass
from typing import Literal

from runtime.db_lock import LockedConnection
from substrate.graph.insight_question import (
    canonical_text,
    insight_node_id,
    promote_insight,
    promote_question,
    question_node_id,
)

from .evidence_promotion import AcceptedTwinPromotionAuthority, TwinEvidencePromotionLedger
from .ledger import TwinRecursionLedger

WRITER_SCHEMA = "antiek.canonical-twin-promotion-writer.v1"


class CanonicalTwinPromotionWriterError(RuntimeError):
    """Accepted authority cannot be materialized exactly and atomically."""


@dataclass(frozen=True)
class CanonicalTwinPromotionResult:
    node_id: str
    candidate_id: str
    review_id: str
    kind: Literal["insight", "question"]
    owner_id: str
    authority: Literal["owner_reviewed_evidence_bound_graph_node_v1"] = (
        "owner_reviewed_evidence_bound_graph_node_v1"
    )


class _NoEmbeddingProvider:
    @staticmethod
    def encode(_text: str) -> None:
        return None


def canonical_promotion_node_id(authority: AcceptedTwinPromotionAuthority) -> str:
    """Return the exact owner-scoped graph identity for an accepted candidate."""
    candidate = authority.candidate
    if candidate.kind == "insight":
        node_id: str = insight_node_id(candidate.text, identity_scope=candidate.owner_id)
        return node_id
    if candidate.kind == "question":
        question_id: str = question_node_id(candidate.text, identity_scope=candidate.owner_id)
        return question_id
    raise CanonicalTwinPromotionWriterError("candidate kind is not materializable")


def canonical_promotion_node_metadata(
    authority: AcceptedTwinPromotionAuthority,
) -> dict[str, object]:
    """Build the complete metadata projection written by the sanctioned graph writer."""
    candidate = authority.candidate
    review = authority.review
    metadata: dict[str, object] = {
        "writer_schema": WRITER_SCHEMA,
        "authority_temporality": "materialization_time",
        "reuse_policy": "revalidate_promotion_authority_before_use",
        "promotion_authority": authority.authority,
        "promotion_schema": candidate.schema,
        "candidate_id": candidate.candidate_id,
        "candidate_digest": review.candidate_digest,
        "review_id": review.review_id,
        "source_asset_id": candidate.source_asset_id,
        "source_hash": candidate.source_hash,
        "binding_id": candidate.binding_id,
        "twin_document_id": candidate.twin_document_id,
        "twin_chunk_id": candidate.twin_chunk_id,
        "twin_chunk_sha256": candidate.twin_chunk_sha256,
        "body_hash": candidate.body_hash,
        "completion_digest": candidate.completion_digest,
        "evidence": [
            {key: value for key, value in asdict(item).items() if key != "text"}
            for item in candidate.evidence
        ],
    }
    metadata.update(
        {
            "promoted_kind": candidate.kind,
            "canonical_text": canonical_text(candidate.text),
            "investigation_id": candidate.candidate_id,
            "identity_scope": candidate.owner_id,
        }
    )
    if candidate.kind == "insight":
        metadata["confidence"] = "unknown"
    elif candidate.kind != "question":
        raise CanonicalTwinPromotionWriterError("candidate kind is not materializable")
    return metadata


def materialize_accepted_twin_promotion(
    con: LockedConnection,
    promotions: TwinEvidencePromotionLedger,
    twins: TwinRecursionLedger,
    *,
    owner_id: str,
    candidate_id: str,
) -> CanonicalTwinPromotionResult:
    """Revalidate and atomically write one exact accepted private graph node."""
    if type(con) is not LockedConnection:
        raise TypeError("canonical promotion requires the exact locked graph connection")
    if type(promotions) is not TwinEvidencePromotionLedger:
        raise TypeError("canonical promotion requires the exact promotion ledger")
    if type(twins) is not TwinRecursionLedger:
        raise TypeError("canonical promotion requires the exact twin ledger")
    try:
        con.execute("BEGIN")
    except Exception as exc:
        raise CanonicalTwinPromotionWriterError(
            "canonical promotion requires ownership of one graph transaction"
        ) from exc
    try:
        with promotions.accepted_snapshot(
            con, twins, owner_id=owner_id, candidate_id=candidate_id
        ) as snapshot:
            authority = snapshot.authority
            candidate = authority.candidate
            metadata = canonical_promotion_node_metadata(authority)
            if candidate.kind == "insight":
                node_id = promote_insight(
                    text=candidate.text,
                    investigation_id=candidate.candidate_id,
                    embedding_provider=_NoEmbeddingProvider(),
                    metadata=metadata,
                    con=con,
                    dedup=False,
                    identity_scope=candidate.owner_id,
                    owner_user_id=candidate.owner_id,
                    emit_graph_events=False,
                )
            elif candidate.kind == "question":
                node_id = promote_question(
                    text=candidate.text,
                    investigation_id=candidate.candidate_id,
                    embedding_provider=_NoEmbeddingProvider(),
                    metadata=metadata,
                    con=con,
                    dedup=False,
                    identity_scope=candidate.owner_id,
                    owner_user_id=candidate.owner_id,
                    emit_graph_events=False,
                )
            else:  # pragma: no cover - closed by Cycle 114, retained as a write guard.
                raise CanonicalTwinPromotionWriterError("candidate kind is not materializable")
            promotions.require_snapshot_current(snapshot)
            con.execute("COMMIT")
            return CanonicalTwinPromotionResult(
                node_id,
                candidate.candidate_id,
                authority.review.review_id,
                candidate.kind,
                candidate.owner_id,
            )
    except Exception:
        with suppress(Exception):
            con.execute("ROLLBACK")
        raise


__all__ = [
    "CanonicalTwinPromotionResult",
    "CanonicalTwinPromotionWriterError",
    "WRITER_SCHEMA",
    "canonical_promotion_node_id",
    "canonical_promotion_node_metadata",
    "materialize_accepted_twin_promotion",
]
