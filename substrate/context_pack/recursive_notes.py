"""Validated, bounded recursive-note content for downstream prompts."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ContentAuthority = Literal["engagement_twin", "depth_graph"]
ContentKind = Literal["insight", "question", "artifact_note"]
ExclusionReason = Literal[
    "aggregate_budget",
    "caller_supplied_advisory",
    "duplicate_content",
    "foreign_owner",
    "malformed",
    "missing_asset",
    "no_content",
    "per_asset_diversity",
    "per_unit_limit",
    "resolver_unavailable",
]

MAX_ID_BYTES = 512
MAX_PROVENANCE_IDS = 32
MAX_REQUEST_ITEMS = 4096
MAX_CANDIDATES = 16_384
MAX_EXCLUSIONS = 65_536
MAX_GOAL_BYTES = 32_768
MAX_SOURCE_TEXT_BYTES = 65_536


def _bounded_id(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned.encode("utf-8")) > MAX_ID_BYTES:
        raise ValueError(f"{field} is invalid")
    return cleaned


def digest_text(text: str) -> str:
    canonical = " ".join(text.split())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def account_scope_digest(owner_user_id: str) -> str:
    owner = _bounded_id(owner_user_id, "owner_user_id")
    return hashlib.sha256(f"antiek-owner-scope-v1\0{owner}".encode()).hexdigest()


@dataclass(frozen=True)
class _ResolvedCandidate:
    authority: ContentAuthority
    asset_id: str
    canonical_id: str
    kind: ContentKind
    text: str
    ordinal: int
    created_at: str | None
    source_event_ids: tuple[str, ...] = ()
    explicit: bool = False

    def __post_init__(self) -> None:
        if self.authority not in {"engagement_twin", "depth_graph"}:
            raise ValueError("candidate authority is invalid")
        if self.kind not in {"insight", "question", "artifact_note"}:
            raise ValueError("candidate kind is invalid")
        _bounded_id(self.asset_id, "asset_id")
        _bounded_id(self.canonical_id, "canonical_id")
        if self.ordinal < 0:
            raise ValueError("candidate ordinal is invalid")
        if not isinstance(self.text, str) or len(self.text.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES:
            raise ValueError("candidate text is invalid")
        if len(self.source_event_ids) > MAX_PROVENANCE_IDS:
            raise ValueError("too many source_event_ids")
        for value in self.source_event_ids:
            _bounded_id(value, "source_event_id")
        if self.created_at is not None:
            if len(self.created_at.encode("utf-8")) > 128:
                raise ValueError("created_at is invalid")
            try:
                datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("created_at is invalid") from exc


@dataclass(frozen=True)
class ContentUnit:
    unit_id: str
    authority: ContentAuthority
    account_scope_digest: str
    asset_id: str
    twin_note_id: str | None
    graph_node_id: str | None
    artifact_note_id: str | None
    kind: ContentKind
    ordinal: int
    created_at: str | None
    text: str
    text_digest: str
    source_event_ids: tuple[str, ...]
    token_estimate: int
    rights_label: Literal["owner_readable"] = "owner_readable"

    def __post_init__(self) -> None:
        _bounded_id(self.unit_id, "unit_id")
        _bounded_id(self.asset_id, "asset_id")
        if len(self.account_scope_digest) != 64 or len(self.text_digest) != 64:
            raise ValueError("content unit digest is invalid")
        canonical_ids = [
            value
            for value in (self.twin_note_id, self.graph_node_id, self.artifact_note_id)
            if value is not None
        ]
        if len(canonical_ids) != 1:
            raise ValueError("content unit requires exactly one canonical source id")
        _bounded_id(canonical_ids[0], "canonical source id")
        if self.authority == "engagement_twin" and self.twin_note_id is None:
            raise ValueError("engagement content requires a twin note id")
        if self.authority == "depth_graph" and self.graph_node_id is None:
            raise ValueError("graph content requires a graph node id")
        if self.ordinal < 0 or self.token_estimate < 1:
            raise ValueError("content unit ordinal or token estimate is invalid")
        if not self.text.strip() or digest_text(self.text) != self.text_digest:
            raise ValueError("content unit text is invalid")
        if len(self.source_event_ids) > MAX_PROVENANCE_IDS:
            raise ValueError("too many source_event_ids")
        for value in self.source_event_ids:
            _bounded_id(value, "source_event_id")


@dataclass(frozen=True)
class AdvisoryPreview:
    unit_id: str
    authority: Literal["caller_supplied_advisory"]
    text: str
    text_digest: str
    token_estimate: int

    def __post_init__(self) -> None:
        _bounded_id(self.unit_id, "advisory unit_id")
        if self.authority != "caller_supplied_advisory":
            raise ValueError("advisory authority is invalid")
        if not self.text.strip() or digest_text(self.text) != self.text_digest:
            raise ValueError("advisory text is invalid")
        if self.token_estimate < 1:
            raise ValueError("advisory token estimate is invalid")


@dataclass(frozen=True)
class ExclusionReceipt:
    authority: str
    candidate_digest: str
    reason: ExclusionReason
    asset_scope_digest: str | None = None

    def __post_init__(self) -> None:
        _bounded_id(self.authority, "exclusion authority")
        if len(self.candidate_digest) != 64:
            raise ValueError("candidate digest is invalid")
        if self.asset_scope_digest is not None and len(self.asset_scope_digest) != 64:
            raise ValueError("asset scope digest is invalid")


@dataclass(frozen=True)
class RecursiveNotesPack:
    units: tuple[ContentUnit, ...]
    exclusions: tuple[ExclusionReceipt, ...]
    token_estimate: int
    token_budget: int
    candidate_count: int
    advisory_previews: tuple[AdvisoryPreview, ...] = ()
    advisory_token_estimate: int = 0

    def __post_init__(self) -> None:
        if self.token_budget < 1 or not 0 <= self.token_estimate <= self.token_budget:
            raise ValueError("pack token accounting is invalid")
        if not 0 <= self.candidate_count <= MAX_CANDIDATES:
            raise ValueError("pack candidate count is invalid")
        if len(self.exclusions) > MAX_EXCLUSIONS:
            raise ValueError("too many exclusion receipts")
        if len(self.units) > MAX_CANDIDATES:
            raise ValueError("too many content units")
        if len(self.advisory_previews) > MAX_EXCLUSIONS:
            raise ValueError("too many advisory previews")
        if (
            self.advisory_token_estimate < 0
            or sum(unit.token_estimate for unit in self.advisory_previews)
            != self.advisory_token_estimate
            or self.token_estimate + self.advisory_token_estimate > self.token_budget
        ):
            raise ValueError("advisory token accounting is invalid")
        if sum(unit.token_estimate for unit in self.units) != self.token_estimate:
            raise ValueError("pack token total does not match units")

    @property
    def pack_ready(self) -> bool:
        return bool(self.units)

    @property
    def truncated(self) -> bool:
        return any(
            receipt.reason in {"aggregate_budget", "per_asset_diversity", "per_unit_limit"}
            for receipt in self.exclusions
        )


def _token_estimate(text: str) -> int:
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


def _receipt(candidate: _ResolvedCandidate, reason: ExclusionReason) -> ExclusionReceipt:
    return ExclusionReceipt(
        authority=candidate.authority,
        candidate_digest=hashlib.sha256(
            f"{candidate.authority}\0{candidate.asset_id}\0{candidate.canonical_id}".encode()
        ).hexdigest(),
        reason=reason,
        asset_scope_digest=hashlib.sha256(candidate.asset_id.encode()).hexdigest(),
    )


def _assemble_resolved_notes_pack(
    candidates: list[_ResolvedCandidate],
    *,
    owner_user_id: str,
    goal: str,
    token_budget: int,
    max_unit_bytes: int,
    max_units: int,
    per_asset_limit: int,
    prior_exclusions: tuple[ExclusionReceipt, ...],
) -> RecursiveNotesPack:
    """Internal-only assembly; canonical callers must enter through resolvers."""

    if len(candidates) > MAX_CANDIDATES or len(prior_exclusions) > MAX_EXCLUSIONS:
        raise ValueError("recursive candidate or exclusion bound exceeded")
    if token_budget < 1 or max_unit_bytes < 1 or max_units < 1 or per_asset_limit < 1:
        raise ValueError("recursive note bounds must be positive")
    if not isinstance(goal, str) or len(goal.encode("utf-8")) > MAX_GOAL_BYTES:
        raise ValueError("recursive note goal is invalid")
    goal_terms = set(goal.casefold().split())

    def recency_key(created_at: str | None) -> tuple[int, tuple[int, ...]]:
        if created_at is None:
            return (1, ())
        return (0, tuple(-ord(character) for character in created_at))

    def rank(candidate: _ResolvedCandidate) -> tuple[object, ...]:
        relevance = len(goal_terms & set(candidate.text.casefold().split()))
        return (
            0 if candidate.explicit else 1,
            -relevance,
            0 if candidate.kind == "question" else 1,
            recency_key(candidate.created_at),
            candidate.ordinal,
            candidate.asset_id,
            candidate.authority,
            candidate.canonical_id,
        )

    ordered = sorted(candidates, key=rank)
    selected: list[ContentUnit] = []
    exclusions = list(prior_exclusions)
    seen_text: set[str] = set()
    per_asset: dict[str, int] = {}
    used_tokens = 0
    scope = account_scope_digest(owner_user_id)
    for candidate in ordered:
        text = " ".join(candidate.text.split()).strip()
        if not text:
            exclusions.append(_receipt(candidate, "malformed"))
            continue
        text_digest = digest_text(text)
        if text_digest in seen_text:
            exclusions.append(_receipt(candidate, "duplicate_content"))
            continue
        if len(text.encode("utf-8")) > max_unit_bytes:
            exclusions.append(_receipt(candidate, "per_unit_limit"))
            continue
        if per_asset.get(candidate.asset_id, 0) >= per_asset_limit:
            exclusions.append(_receipt(candidate, "per_asset_diversity"))
            continue
        tokens = _token_estimate(text)
        if len(selected) >= max_units or used_tokens + tokens > token_budget:
            exclusions.append(_receipt(candidate, "aggregate_budget"))
            continue
        unit_id = hashlib.sha256(
            f"recursive-content-v1\0{candidate.authority}\0{candidate.asset_id}"
            f"\0{candidate.canonical_id}\0{text_digest}".encode()
        ).hexdigest()
        selected.append(
            ContentUnit(
                unit_id=unit_id,
                authority=candidate.authority,
                account_scope_digest=scope,
                asset_id=candidate.asset_id,
                twin_note_id=(
                    candidate.canonical_id if candidate.authority == "engagement_twin" else None
                ),
                graph_node_id=(
                    candidate.canonical_id if candidate.authority == "depth_graph" else None
                ),
                artifact_note_id=None,
                kind=candidate.kind,
                ordinal=candidate.ordinal,
                created_at=candidate.created_at,
                text=text,
                text_digest=text_digest,
                source_event_ids=candidate.source_event_ids,
                token_estimate=tokens,
            )
        )
        seen_text.add(text_digest)
        per_asset[candidate.asset_id] = per_asset.get(candidate.asset_id, 0) + 1
        used_tokens += tokens
    return RecursiveNotesPack(
        units=tuple(selected),
        exclusions=tuple(exclusions),
        token_estimate=used_tokens,
        token_budget=token_budget,
        candidate_count=len(candidates),
    )
