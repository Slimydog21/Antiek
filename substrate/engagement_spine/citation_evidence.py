"""Strict downstream value for server-validated synthesis citation receipts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _identifier(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > 512
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError(f"citation {name} is invalid")
    return value


@dataclass(frozen=True)
class CitationEvidence:
    source_kind: str
    source_asset_id: str
    claim_id: str
    chunk_ids: tuple[str, ...]
    document_id: str
    receipt_sha256: str

    def authority_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_asset_id": self.source_asset_id,
            "claim_id": self.claim_id,
            "chunk_ids": list(self.chunk_ids),
            "document_id": self.document_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.authority_dict(), "receipt_sha256": self.receipt_sha256}

    def prompt_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def parse_citation_evidence(value: object) -> CitationEvidence | None:
    """Parse a persisted receipt; absence is uncited, malformed is an error."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("citation provenance receipt is malformed")
    if set(value) != {
        "source_kind", "source_asset_id", "claim_id", "chunk_ids", "document_id"
    }:
        raise ValueError("citation provenance receipt fields are invalid")
    if value.get("source_kind") != "synthesis_claim":
        raise ValueError("citation source_kind is invalid")
    raw_chunks = value.get("chunk_ids")
    if not isinstance(raw_chunks, list) or not raw_chunks or len(raw_chunks) > 64:
        raise ValueError("citation chunk_ids are invalid")
    chunks = tuple(_identifier(item, "chunk_id") for item in raw_chunks)
    if len(set(chunks)) != len(chunks):
        raise ValueError("citation chunk_ids must be unique")
    authority = {
        "source_kind": "synthesis_claim",
        "source_asset_id": _identifier(value.get("source_asset_id"), "source_asset_id"),
        "claim_id": _identifier(value.get("claim_id"), "claim_id"),
        "chunk_ids": list(chunks),
        "document_id": _identifier(value.get("document_id"), "document_id"),
    }
    canonical = json.dumps(authority, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return CitationEvidence(
        source_kind=authority["source_kind"],
        source_asset_id=authority["source_asset_id"],
        claim_id=authority["claim_id"],
        chunk_ids=chunks,
        document_id=authority["document_id"],
        receipt_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


__all__ = ["CitationEvidence", "parse_citation_evidence"]
