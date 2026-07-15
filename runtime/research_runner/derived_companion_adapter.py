"""Pure, fail-closed adapter contract for derived companion answers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from substrate.research_artifact.grounded_companion_answer import (
    GroundedAnswerError,
    candidate_from_json,
)

from .provider_qualification import ProviderQualification

_SHA256 = re.compile(r"[0-9a-f]{64}")
_RESPONSE_ID = re.compile(r"[A-Za-z0-9._:-]{1,512}")
_ResponseT = TypeVar("_ResponseT", contravariant=True)
_AdapterT = TypeVar("_AdapterT", bound="CompanionAnswerAdapter[Any]")


class CompanionAdapterError(RuntimeError):
    """The adapter boundary is invalid or not authorized by both gates."""


@dataclass(frozen=True, order=True)
class CompanionAdapterRoute:
    provider: str
    model: str
    operation: str = "answer"

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("companion adapter provider and model are required")
        if self.provider != self.provider.strip() or self.model != self.model.strip():
            raise ValueError("companion adapter identity must be canonical text")
        if self.operation != "answer":
            raise ValueError("companion adapter operation must be answer")

    @property
    def route_key(self) -> tuple[str, str, str]:
        return self.provider, self.model, self.operation


@dataclass(frozen=True)
class ProviderResponseEvidence:
    """Bounded, secret-free material used to derive response provenance."""

    provider_response_id: str
    response_body_sha256: str
    usage_sha256: str

    def __post_init__(self) -> None:
        if (
            _RESPONSE_ID.fullmatch(self.provider_response_id) is None
        ):
            raise ValueError("provider response identity is invalid")
        if (
            _SHA256.fullmatch(self.response_body_sha256) is None
            or _SHA256.fullmatch(self.usage_sha256) is None
        ):
            raise ValueError("provider response evidence hashes must be lowercase SHA-256")


@dataclass(frozen=True)
class NormalizedCompanionSuccess:
    candidate_json: str
    response_evidence: ProviderResponseEvidence

    def __post_init__(self) -> None:
        try:
            candidate_from_json(self.candidate_json)
        except GroundedAnswerError as exc:
            raise ValueError("adapter returned an invalid canonical candidate") from exc
        if not isinstance(self.response_evidence, ProviderResponseEvidence):
            raise TypeError("adapter response evidence is invalid")

    @property
    def provider_response_digest(self) -> str:
        payload = json.dumps(
            {
                "provider_response_id": self.response_evidence.provider_response_id,
                "response_body_sha256": self.response_evidence.response_body_sha256,
                "usage_sha256": self.response_evidence.usage_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CompanionAnswerAdapter(Protocol[_ResponseT]):
    """An injected adapter that purely normalizes its private success type."""

    @property
    def route(self) -> CompanionAdapterRoute: ...

    def normalize_success(self, response: _ResponseT) -> NormalizedCompanionSuccess: ...


class CompanionAdapterRegistry:
    """Immutable exact-route registry; empty construction grants no authority."""

    def __init__(self, adapters: tuple[CompanionAnswerAdapter[Any], ...] = ()) -> None:
        indexed: dict[tuple[str, str, str], CompanionAnswerAdapter[Any]] = {}
        for adapter in adapters:
            route = adapter.route
            if not isinstance(route, CompanionAdapterRoute):
                raise TypeError("companion adapter route is invalid")
            if route.route_key in indexed:
                raise CompanionAdapterError("duplicate companion adapter route")
            indexed[route.route_key] = adapter
        self._adapters = indexed

    def contains(
        self, route: CompanionAdapterRoute, adapter: CompanionAnswerAdapter[Any]
    ) -> bool:
        return self._adapters.get(route.route_key) is adapter

    def __len__(self) -> int:
        return len(self._adapters)


def select_qualified_companion_adapter(  # noqa: UP047 -- runtime supports Python 3.11
    route: CompanionAdapterRoute,
    qualifications: tuple[ProviderQualification, ...],
    registry: CompanionAdapterRegistry,
    adapter: _AdapterT,
) -> _AdapterT:
    """Require one exact fully-qualified record and one exact registered adapter."""
    matching = [item for item in qualifications if item.route_key == route.route_key]
    if len(matching) > 1:
        raise CompanionAdapterError("duplicate companion route qualifications")
    if not matching or not matching[0].fully_qualified:
        raise CompanionAdapterError("companion route is not fully qualified")
    if not registry.contains(route, adapter):
        raise CompanionAdapterError("qualified companion route is not registered")
    return adapter


__all__ = [
    "CompanionAdapterError",
    "CompanionAdapterRegistry",
    "CompanionAdapterRoute",
    "CompanionAnswerAdapter",
    "NormalizedCompanionSuccess",
    "ProviderResponseEvidence",
    "select_qualified_companion_adapter",
]
