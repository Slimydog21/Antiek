"""Universal-library ingestion backend (Sprint SPR-03).

URL paste → content-type-aware fetch → extract (HTML / PDF / EPUB /
arXiv) → unified pipeline that calls the existing chunker, embedder,
edge-builder. CLI and HTTP API are the only surfaces; consumer UI
lands in SPR-06.

Inherits the working arXiv ingestion (PDF endpoint + S2 fallback)
from ``acquisition/arxiv/`` and the URL HTML extractor from
``acquisition/urls/`` rather than reinventing — see rigor #4 in the
sprint HTML for the diligence rationale.

Fixes the known arXiv failure modes (memory ``project_researchmaxx_arxiv``,
2026-05-17): in-process throttle → Redis-backed sliding window with
persistent ``banned_until`` sentinel; missing SSL env exports loaded
at startup; metadata cache sized 10× the legacy.
"""
