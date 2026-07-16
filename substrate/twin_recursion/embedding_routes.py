"""Deny-by-default server route registry for canonical twin embedding."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from runtime.research_runner.protocol import CostProjectionRequest
from runtime.research_runner.provider_gateway import HardCeilingProviderAdapter


class CanonicalEmbeddingRouteUnavailable(LookupError):
    """No exact server-qualified route is available."""


def _route_id(value: object) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 128
        or value.strip() != value
        or any(
            not (character.isascii() and (character.isalnum() or character in "._-"))
            for character in value
        )
    ):
        raise ValueError("route_id must be a bounded opaque ASCII identifier")
    return value


@dataclass(frozen=True)
class QualifiedCanonicalEmbeddingRoute:
    route_id: str
    projection_request: CostProjectionRequest
    adapter: HardCeilingProviderAdapter[Any]

    def __post_init__(self) -> None:
        _route_id(self.route_id)
        if type(self.projection_request) is not CostProjectionRequest:
            raise TypeError("route requires the exact cost projection request")
        adapter = self.adapter
        dimension = getattr(adapter, "dimension", None)
        if (
            (adapter.provider, adapter.model)
            != (self.projection_request.provider, self.projection_request.model)
            or isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or not 1 <= dimension <= 65_536
        ):
            raise ValueError("route adapter differs from its server projection identity")
        if not adapter.capabilities.hard_ceiling_eligible:
            raise ValueError("route adapter is not hard-ceiling eligible")


class CanonicalEmbeddingRouteRegistry:
    """Immutable registry; an empty instance is the production default."""

    def __init__(self, routes: tuple[QualifiedCanonicalEmbeddingRoute, ...] = ()) -> None:
        if type(routes) is not tuple or any(
            type(route) is not QualifiedCanonicalEmbeddingRoute for route in routes
        ):
            raise TypeError("registry routes must be an exact immutable tuple")
        values: dict[str, QualifiedCanonicalEmbeddingRoute] = {}
        for route in routes:
            if route.route_id in values:
                raise ValueError("canonical embedding route ids must be unique")
            values[route.route_id] = route
        self._routes: Mapping[str, QualifiedCanonicalEmbeddingRoute] = MappingProxyType(values)

    def resolve(self, route_id: str) -> QualifiedCanonicalEmbeddingRoute:
        try:
            normalized = _route_id(route_id)
        except ValueError as exc:
            raise CanonicalEmbeddingRouteUnavailable("embedding route unavailable") from exc
        route = self._routes.get(normalized)
        if route is None:
            raise CanonicalEmbeddingRouteUnavailable("embedding route unavailable")
        return route

    @property
    def available(self) -> bool:
        return bool(self._routes)


__all__ = [
    "CanonicalEmbeddingRouteRegistry",
    "CanonicalEmbeddingRouteUnavailable",
    "QualifiedCanonicalEmbeddingRoute",
]
