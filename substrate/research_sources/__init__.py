"""Deep-research source readiness probes (arxiv / Substack / corpus / web).

Offline-first: import real acquisition adapters and exercise injectable
client seams without network. Preflight surfaces consume these probes so
DRW source-policy notes stay honest (not forever-hardcoded "gated").
"""

from .readiness import (
    SourceReadiness,
    probe_arxiv,
    probe_source,
    probe_substack,
)

__all__ = [
    "SourceReadiness",
    "probe_arxiv",
    "probe_source",
    "probe_substack",
]
