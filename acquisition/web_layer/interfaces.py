"""Vendor-neutral contracts for the web layer.

Credentials are deliberately absent from these interfaces.  Each concrete adapter
receives only its own vendor key, so replacing extraction cannot expose discovery
credentials (and vice versa).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from acquisition.web_layer.cost import CostRecord


@dataclass(frozen=True, slots=True)
class DiscoveryHit:
    """A URL proposed by discovery; downstream code decides whether to fetch it."""

    url: str
    title: str
    score: float | None
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Full retrieved text and provenance needed to construct downstream spans."""

    source_url: str
    text: str
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class DiscoveryResponse:
    results: tuple[DiscoveryHit, ...]
    cost: CostRecord
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class ExtractionResponse:
    result: ExtractionResult
    cost: CostRecord


class DiscoveryAdapter(Protocol):
    """Find URLs without fetching or ingesting them."""

    def search(self, query: str, *, limit: int) -> DiscoveryResponse: ...

    def find_similar(self, seed_url: str, *, limit: int) -> DiscoveryResponse: ...


class ExtractionAdapter(Protocol):
    """Read a caller-selected discovery URL using GET-only retrieval."""

    def extract(self, url: str) -> ExtractionResponse: ...
