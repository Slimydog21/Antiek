"""Injectable discovery and extraction adapters for public web acquisition."""

from acquisition.web_layer.cost import CostRecord, estimate_cost
from acquisition.web_layer.interfaces import (
    DiscoveryAdapter,
    DiscoveryHit,
    ExtractionAdapter,
    ExtractionResult,
)
from acquisition.web_layer.pipeline import FirstHitsSelector, PipelineResult, WebPipeline

__all__ = [
    "CostRecord",
    "DiscoveryAdapter",
    "DiscoveryHit",
    "ExtractionAdapter",
    "ExtractionResult",
    "FirstHitsSelector",
    "PipelineResult",
    "WebPipeline",
    "estimate_cost",
]
