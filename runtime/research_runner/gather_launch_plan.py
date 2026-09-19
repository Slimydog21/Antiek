"""Launch-reviewed template that materializes one gather plan per cascade leaf."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from runtime.research_runner.gather_plan import AuthorizedGatherPlan, GatherSourcePlan
from substrate.investigation_tenancy import InvestigationAuthority


@dataclass(frozen=True, slots=True)
class AuthorizedGatherLaunchPlan:
    """One review fingerprint for a bounded cascade fan-out.

    Provider receipts are query-specific and therefore cannot be shared across
    leaves.  This template binds the root review and total exposure while
    materializing a distinct investigation-bound plan for every child.
    """

    version: int
    account_digest: str
    root_investigation_digest: str
    legal_policy_snapshot_sha256: str
    leaf_count: int
    per_leaf_max_results: int
    per_leaf_max_cost_micros: int
    launch_max_results: int
    launch_max_cost_micros: int
    leaf_query_sha256: tuple[str, ...]
    sources: tuple[GatherSourcePlan, ...]

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version != 1:
            raise ValueError("unsupported gather launch plan version")
        for value, label in (
            (self.account_digest, "account_digest"),
            (self.root_investigation_digest, "root_investigation_digest"),
            (self.legal_policy_snapshot_sha256, "legal_policy_snapshot_sha256"),
        ):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"{label} must be 64 lowercase hex characters")
        for value, label in (
            (self.leaf_count, "leaf_count"),
            (self.per_leaf_max_results, "per_leaf_max_results"),
            (self.per_leaf_max_cost_micros, "per_leaf_max_cost_micros"),
            (self.launch_max_results, "launch_max_results"),
            (self.launch_max_cost_micros, "launch_max_cost_micros"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{label} must be a non-negative integer")
        if not 1 <= self.leaf_count <= 256:
            raise ValueError("leaf_count must be from 1 through 256")
        if not self.sources:
            raise ValueError("gather launch plan requires at least one source")
        if len(self.leaf_query_sha256) != self.leaf_count or any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in self.leaf_query_sha256
        ):
            raise ValueError("leaf query digests must match the reviewed fan-out")
        if self.per_leaf_max_results != sum(item.max_results for item in self.sources):
            raise ValueError("per-leaf result exposure does not match sources")
        if self.per_leaf_max_cost_micros != sum(item.max_cost_micros for item in self.sources):
            raise ValueError("per-leaf cost exposure does not match sources")
        if self.launch_max_results != self.per_leaf_max_results * self.leaf_count:
            raise ValueError("launch result exposure does not match leaf fan-out")
        if self.launch_max_cost_micros != self.per_leaf_max_cost_micros * self.leaf_count:
            raise ValueError("launch cost exposure does not match leaf fan-out")
        # Reuse the canonical source-order and direct-constructor validation.
        AuthorizedGatherPlan(
            1,
            self.account_digest,
            self.root_investigation_digest,
            self.legal_policy_snapshot_sha256,
            self.per_leaf_max_results,
            self.per_leaf_max_cost_micros,
            self.sources,
        )

    @classmethod
    def reviewed(
        cls,
        authority: InvestigationAuthority,
        *,
        legal_policy_snapshot_sha256: str,
        leaf_queries: tuple[str, ...],
        sources: tuple[GatherSourcePlan, ...],
    ) -> AuthorizedGatherLaunchPlan:
        normalized_queries = tuple(query.strip() for query in leaf_queries)
        if not normalized_queries or any(not query for query in normalized_queries):
            raise ValueError("leaf queries must be non-empty")
        query_digests = tuple(
            hashlib.sha256(query.encode("utf-8")).hexdigest() for query in normalized_queries
        )
        leaf_count = len(normalized_queries)
        per_leaf_results = sum(item.max_results for item in sources)
        per_leaf_cost = sum(item.max_cost_micros for item in sources)
        return cls(
            1,
            authority.account_digest,
            authority.investigation_digest,
            legal_policy_snapshot_sha256,
            leaf_count,
            per_leaf_results,
            per_leaf_cost,
            per_leaf_results * leaf_count,
            per_leaf_cost * leaf_count,
            query_digests,
            sources,
        )

    def canonical_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "account_digest": self.account_digest,
            "root_investigation_digest": self.root_investigation_digest,
            "legal_policy_snapshot_sha256": self.legal_policy_snapshot_sha256,
            "leaf_count": self.leaf_count,
            "per_leaf_max_results": self.per_leaf_max_results,
            "per_leaf_max_cost_micros": self.per_leaf_max_cost_micros,
            "launch_max_results": self.launch_max_results,
            "launch_max_cost_micros": self.launch_max_cost_micros,
            "leaf_query_sha256": list(self.leaf_query_sha256),
            "sources": [source.canonical_dict() for source in self.sources],
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.canonical_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def materialize_leaf(
        self, authority: InvestigationAuthority, *, leaf_index: int, query: str
    ) -> AuthorizedGatherPlan:
        if authority.account_digest != self.account_digest:
            raise ValueError("leaf authority belongs to a different account")
        if authority.investigation_digest == self.root_investigation_digest:
            raise ValueError("leaf gather authority must be distinct from the root")
        if isinstance(leaf_index, bool) or not isinstance(leaf_index, int) or not (
            0 <= leaf_index < self.leaf_count
        ):
            raise ValueError("leaf index is outside the reviewed fan-out")
        if hashlib.sha256(query.strip().encode("utf-8")).hexdigest() != self.leaf_query_sha256[
            leaf_index
        ]:
            raise ValueError("leaf query differs from the reviewed launch plan")
        return AuthorizedGatherPlan(
            1,
            self.account_digest,
            authority.investigation_digest,
            self.legal_policy_snapshot_sha256,
            self.per_leaf_max_results,
            self.per_leaf_max_cost_micros,
            self.sources,
        )


__all__ = ["AuthorizedGatherLaunchPlan"]
