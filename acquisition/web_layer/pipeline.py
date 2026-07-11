"""Composition of discovery, explicit bounded selection, and extraction."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from acquisition.web_layer.cost import CostRecord
from acquisition.web_layer.interfaces import (
    DiscoveryAdapter,
    DiscoveryHit,
    ExtractionAdapter,
    ExtractionResult,
)


class HitSelector(Protocol):
    """Select only from discovery output; never construct arbitrary URLs."""

    def select(
        self, hits: tuple[DiscoveryHit, ...], *, limit: int
    ) -> tuple[DiscoveryHit, ...]: ...


class FirstHitsSelector:
    """Deterministic reference selector retaining discovery rank order."""

    def select(
        self, hits: tuple[DiscoveryHit, ...], *, limit: int
    ) -> tuple[DiscoveryHit, ...]:
        if limit < 0:
            raise ValueError("extraction limit must be non-negative")
        return hits[:limit]


@dataclass(frozen=True, slots=True)
class PipelineResult:
    discovered: tuple[DiscoveryHit, ...]
    selected: tuple[DiscoveryHit, ...]
    extracted: tuple[ExtractionResult, ...]
    costs: tuple[CostRecord, ...]
    total_usd_estimate: Decimal


class WebPipeline:
    """Run search then GET-only extraction for a selected result subset."""

    def __init__(
        self,
        *,
        discovery: DiscoveryAdapter,
        extraction: ExtractionAdapter,
        selector: HitSelector,
    ) -> None:
        self._discovery = discovery
        self._extraction = extraction
        self._selector = selector

    def search_and_extract(
        self,
        query: str,
        *,
        discovery_limit: int,
        extraction_limit: int,
    ) -> PipelineResult:
        discovery_response = self._discovery.search(query, limit=discovery_limit)
        selected = self._selector.select(
            discovery_response.results, limit=extraction_limit
        )
        if any(hit not in discovery_response.results for hit in selected):
            raise ValueError("selector returned a hit that discovery did not produce")

        extraction_responses = tuple(
            self._extraction.extract(hit.url) for hit in selected
        )
        costs = (discovery_response.cost,) + tuple(
            response.cost for response in extraction_responses
        )
        return PipelineResult(
            discovered=discovery_response.results,
            selected=selected,
            extracted=tuple(response.result for response in extraction_responses),
            costs=costs,
            total_usd_estimate=sum(
                (cost.usd_estimate for cost in costs), start=Decimal("0")
            ),
        )
