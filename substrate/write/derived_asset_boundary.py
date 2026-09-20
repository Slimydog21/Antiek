"""SPR-00 boundary primitives; no database, filesystem, route, or provider authority."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

LEGACY_SOURCE_MERGE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "draft_merge_path",
        "compose_index_path",
        "source_document_id",
        "owner_user_id",
        "operator_reviewer",
        "commit_id",
        "revision_id",
        "acknowledge_body_rewrite",
    }
)
DERIVED_ASSET_COMMIT_FIELDS: Final[frozenset[str]] = frozenset(
    {"review_id", "acknowledgement", "idempotency_key"}
)
_FORBIDDEN_WRITE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\b(?:insert\s+into|update|delete\s+from)\s+documents\b",
        r"\b(?:insert\s+into|update|delete\s+from)\s+html_projections\b",
        r"\.write_(?:text|bytes)\(",
        r"\bsource_merge_(?:revisions|body_commits|body_restores)\b",
    )
)


class LegacySourceMergeContractRejected(ValueError):
    """Closed refusal that a future FastAPI adapter maps directly to HTTP 422."""

    status_code: Final[int] = 422
    code: Final[str] = "legacy_source_merge_contract_rejected"
    message: Final[str] = (
        "Source evidence cannot be rewritten. Create a server-owned merge "
        "draft and commit it as an operator-owned derived asset revision."
    )

    def __init__(self, rejected_fields: tuple[str, ...]) -> None:
        self.rejected_fields = rejected_fields
        super().__init__(self.message)


class UnknownDerivedAssetCommitField(ValueError):
    """Generic closed refusal for non-legacy extra fields."""

    status_code: Final[int] = 422
    code: Final[str] = "unknown_derived_asset_commit_field"

    def __init__(self, rejected_fields: tuple[str, ...]) -> None:
        self.rejected_fields = rejected_fields
        super().__init__(f"unknown derived-asset commit fields: {', '.join(rejected_fields)}")


def validate_commit_boundary(payload: Mapping[str, object]) -> dict[str, object]:
    """Accept only the future ID-only commit envelope; reject before I/O."""

    supplied = frozenset(payload)
    legacy = tuple(sorted(supplied & LEGACY_SOURCE_MERGE_FIELDS))
    if legacy:
        raise LegacySourceMergeContractRejected(legacy)
    rejected = tuple(sorted(supplied - DERIVED_ASSET_COMMIT_FIELDS))
    if rejected:
        raise UnknownDerivedAssetCommitField(rejected)
    missing = sorted(DERIVED_ASSET_COMMIT_FIELDS - supplied)
    if missing:
        raise ValueError(f"missing derived-asset commit fields: {', '.join(missing)}")
    return {field: payload[field] for field in sorted(DERIVED_ASSET_COMMIT_FIELDS)}


def forbidden_evidence_write_patterns(source: str) -> tuple[str, ...]:
    """Return every immutable-evidence write pattern found in Python source."""

    return tuple(pattern.pattern for pattern in _FORBIDDEN_WRITE_PATTERNS if pattern.search(source))


__all__ = [
    "DERIVED_ASSET_COMMIT_FIELDS",
    "LEGACY_SOURCE_MERGE_FIELDS",
    "LegacySourceMergeContractRejected",
    "UnknownDerivedAssetCommitField",
    "forbidden_evidence_write_patterns",
    "validate_commit_boundary",
]
