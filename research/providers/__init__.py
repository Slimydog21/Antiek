"""Research providers — the adapter package behind ``ResearchProvider``.

This is the **one owner** for engine SDK imports (INV-1). Modules under
``research/providers/`` are permitted to import an engine SDK
(``acquisition.search.exa``, a future Parallel SDK); modules outside
this package are NOT (enforced by ``tests/research/test_one_owner_lint.py``).

Exports:
* ``ResearchResult``, ``RawRef``, ``Source``, ``CostModel`` — the
  normalized result + capability data shapes (``types``).
* ``ResearchProvider`` — the interface (``base``).
* ``conformance`` — the reusable conformance harness.
* ``StubResearchProvider`` — the in-memory stub (``stub``).
"""

from __future__ import annotations

from research.providers.base import ResearchProvider
from research.providers.conformance import ConformanceError, conformance
from research.providers.stub import StubResearchProvider
from research.providers.types import (
    CostModel,
    RawRef,
    ResearchResult,
    Source,
)

__all__ = [
    "ConformanceError",
    "CostModel",
    "RawRef",
    "ResearchProvider",
    "ResearchResult",
    "Source",
    "StubResearchProvider",
    "conformance",
]
