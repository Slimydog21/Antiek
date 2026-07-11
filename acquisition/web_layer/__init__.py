"""Injectable discovery and extraction adapters for public web acquisition."""

from acquisition.web_layer.cost import CostRecord, estimate_cost
from acquisition.web_layer.interfaces import (
    DiscoveryAdapter,
    DiscoveryHit,
    ExtractionAdapter,
    ExtractionResult,
)

__all__ = [
    "CostRecord",
    "DiscoveryAdapter",
    "DiscoveryHit",
    "ExtractionAdapter",
    "ExtractionResult",
    "estimate_cost",
]
