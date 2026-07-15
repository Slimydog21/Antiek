"""Deterministic evidence authority for exact-revision companion turns."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from substrate.research_artifact.derived_asset_retrieval import search_derived_asset

EVIDENCE_PACK_VERSION: Final = "derived_revision_evidence_v1"
DEFAULT_TOP_K: Final = 6


def build_derived_revision_evidence_pack(
    *,
    db_path: str,
    owner_user_id: str,
    asset_id: str,
    question: str,
    revision_id: str | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Build one canonical pack from the already re-derived revision index."""
    retrieval = search_derived_asset(
        db_path=db_path,
        owner_user_id=owner_user_id,
        asset_id=asset_id,
        query=question,
        revision_id=revision_id,
        top_k=top_k,
    )
    normalized_question = question.strip()
    citations = [
        {
            "citation_id": item["citation_id"],
            "chunk_ordinal": item["chunk_ordinal"],
            "member_index": item["member_index"],
            "section_anchor": item["section_anchor"],
            "section_path": item["section_path"],
            "text": item["text"],
            "text_sha256": item["text_sha256"],
        }
        for item in retrieval["results"]
    ]
    payload: dict[str, Any] = {
        "version": EVIDENCE_PACK_VERSION,
        "derived_asset_id": retrieval["derived_asset_id"],
        "revision_id": retrieval["revision_id"],
        "content_sha256": retrieval["content_sha256"],
        "generation": retrieval["generation"],
        "is_current": retrieval["is_current"],
        "index_sha256": retrieval["index_sha256"],
        "chunker": {
            "policy": retrieval["chunker_policy"],
            "version": retrieval["chunker_version"],
        },
        "retrieval": {
            "mode": retrieval["retrieval_mode"],
            "query_sha256": _sha(normalized_question),
            "top_k": top_k,
        },
        "citations": citations,
    }
    payload["pack_sha256"] = _sha(_canonical_json(payload))
    return payload


def canonical_evidence_json(pack: dict[str, Any]) -> str:
    """Serialize a pack for immutable audit persistence."""
    return _canonical_json(pack)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "DEFAULT_TOP_K",
    "EVIDENCE_PACK_VERSION",
    "build_derived_revision_evidence_pack",
    "canonical_evidence_json",
]
