"""Canonical, side-effect-free authority for multi-source research gather.

The plan is deliberately pure: constructing or fingerprinting it cannot read
environment variables, inspect credentials, create provider clients, or spend.
Network adapters consume this reviewed value in a later execution layer.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from substrate.investigation_tenancy import InvestigationAuthority


class GatherSource(StrEnum):
    EXA = "exa"
    PARALLEL = "parallel"
    ARXIV = "arxiv"
    SUBSTACK = "substack"


_CANONICAL_SOURCE_ORDER = tuple(GatherSource)


def _usd_to_micros(value: Decimal | str | int) -> int:
    if isinstance(value, (float, bool)):
        raise ValueError("max_cost_usd must be a decimal amount, never a float")
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("max_cost_usd must be a decimal amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("max_cost_usd must be finite and non-negative")
    micros = amount * 1_000_000
    if micros != micros.quantize(Decimal("1"), rounding=ROUND_HALF_UP):
        raise ValueError("max_cost_usd supports at most six decimal places")
    return int(micros)


@dataclass(frozen=True, slots=True)
class GatherSourcePlan:
    source: GatherSource
    max_results: int
    max_cost_micros: int
    policy_version: str
    source_configuration_sha256: str = "0" * 64

    def __post_init__(self) -> None:
        if not isinstance(self.source, GatherSource):
            raise ValueError("source must be a GatherSource")
        if isinstance(self.max_results, bool) or not isinstance(self.max_results, int):
            raise ValueError("max_results must be an integer")
        if not 1 <= self.max_results <= 100:
            raise ValueError("max_results must be an integer from 1 through 100")
        if isinstance(self.max_cost_micros, bool) or not isinstance(self.max_cost_micros, int):
            raise ValueError("max_cost_micros must be an integer")
        if self.max_cost_micros < 0:
            raise ValueError("max_cost_micros must be non-negative")
        if not self.policy_version.strip() or len(self.policy_version) > 128:
            raise ValueError("policy_version must contain 1 through 128 characters")
        if len(self.source_configuration_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.source_configuration_sha256
        ):
            raise ValueError("source_configuration_sha256 must be 64 lowercase hex characters")

    @classmethod
    def reviewed(
        cls,
        *,
        source: GatherSource | str,
        max_results: int,
        max_cost_usd: Decimal | str | int,
        policy_version: str,
        source_configuration_sha256: str = "0" * 64,
    ) -> GatherSourcePlan:
        resolved_source = GatherSource(source)
        if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 100:
            raise ValueError("max_results must be an integer from 1 through 100")
        normalized_policy_version = policy_version.strip()
        if not normalized_policy_version or len(normalized_policy_version) > 128:
            raise ValueError("policy_version must contain 1 through 128 characters")
        return cls(
            source=resolved_source,
            max_results=max_results,
            max_cost_micros=_usd_to_micros(max_cost_usd),
            policy_version=normalized_policy_version,
            source_configuration_sha256=source_configuration_sha256,
        )

    def canonical_dict(self) -> dict[str, object]:
        return {
            "source": self.source.value,
            "max_results": self.max_results,
            "max_cost_micros": self.max_cost_micros,
            "policy_version": self.policy_version,
            "source_configuration_sha256": self.source_configuration_sha256,
        }


@dataclass(frozen=True, slots=True)
class AuthorizedGatherPlan:
    version: int
    account_digest: str
    investigation_digest: str
    legal_policy_snapshot_sha256: str
    aggregate_max_results: int
    aggregate_max_cost_micros: int
    sources: tuple[GatherSourcePlan, ...]

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version != 1:
            raise ValueError("unsupported gather plan version")
        for value, label in (
            (self.account_digest, "account_digest"),
            (self.investigation_digest, "investigation_digest"),
            (self.legal_policy_snapshot_sha256, "legal_policy_snapshot_sha256"),
        ):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"{label} must be 64 lowercase hex characters")
        if isinstance(self.aggregate_max_results, bool) or not isinstance(
            self.aggregate_max_results, int
        ):
            raise ValueError("aggregate_max_results must be an integer")
        if not 1 <= self.aggregate_max_results <= 400:
            raise ValueError("aggregate_max_results must be an integer from 1 through 400")
        if isinstance(self.aggregate_max_cost_micros, bool) or not isinstance(
            self.aggregate_max_cost_micros, int
        ):
            raise ValueError("aggregate_max_cost_micros must be an integer")
        if self.aggregate_max_cost_micros < 0:
            raise ValueError("aggregate_max_cost_micros must be non-negative")
        if not self.sources:
            raise ValueError("at least one gather source is required")
        if len({item.source for item in self.sources}) != len(self.sources):
            raise ValueError("gather sources must be unique")
        expected_order = tuple(
            source for source in _CANONICAL_SOURCE_ORDER if source in {item.source for item in self.sources}
        )
        if tuple(item.source for item in self.sources) != expected_order:
            raise ValueError("gather sources must use canonical order: exa, parallel, arxiv, substack")
        if sum(item.max_results for item in self.sources) > self.aggregate_max_results:
            raise ValueError("per-source result caps exceed aggregate_max_results")
        if sum(item.max_cost_micros for item in self.sources) > self.aggregate_max_cost_micros:
            raise ValueError("per-source cost caps exceed aggregate_max_cost_usd")

    @classmethod
    def reviewed(
        cls,
        authority: InvestigationAuthority,
        *,
        legal_policy_snapshot_sha256: str,
        aggregate_max_results: int,
        aggregate_max_cost_usd: Decimal | str | int,
        sources: Iterable[GatherSourcePlan],
    ) -> AuthorizedGatherPlan:
        if (
            isinstance(aggregate_max_results, bool)
            or not isinstance(aggregate_max_results, int)
            or not 1 <= aggregate_max_results <= 400
        ):
            raise ValueError("aggregate_max_results must be an integer from 1 through 400")
        snapshot = legal_policy_snapshot_sha256.strip().lower()
        if len(snapshot) != 64 or any(c not in "0123456789abcdef" for c in snapshot):
            raise ValueError("legal_policy_snapshot_sha256 must be 64 lowercase hex characters")

        source_tuple = tuple(sources)
        if not source_tuple:
            raise ValueError("at least one gather source is required")
        if len({item.source for item in source_tuple}) != len(source_tuple):
            raise ValueError("gather sources must be unique")
        expected_order = tuple(source for source in _CANONICAL_SOURCE_ORDER if source in {
            item.source for item in source_tuple
        })
        if tuple(item.source for item in source_tuple) != expected_order:
            raise ValueError("gather sources must use canonical order: exa, parallel, arxiv, substack")

        aggregate_cost = _usd_to_micros(aggregate_max_cost_usd)
        if sum(item.max_results for item in source_tuple) > aggregate_max_results:
            raise ValueError("per-source result caps exceed aggregate_max_results")
        if sum(item.max_cost_micros for item in source_tuple) > aggregate_cost:
            raise ValueError("per-source cost caps exceed aggregate_max_cost_usd")

        return cls(
            version=1,
            account_digest=authority.account_digest,
            investigation_digest=authority.investigation_digest,
            legal_policy_snapshot_sha256=snapshot,
            aggregate_max_results=aggregate_max_results,
            aggregate_max_cost_micros=aggregate_cost,
            sources=source_tuple,
        )

    def canonical_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "account_digest": self.account_digest,
            "investigation_digest": self.investigation_digest,
            "legal_policy_snapshot_sha256": self.legal_policy_snapshot_sha256,
            "aggregate_max_results": self.aggregate_max_results,
            "aggregate_max_cost_micros": self.aggregate_max_cost_micros,
            "sources": [source.canonical_dict() for source in self.sources],
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
