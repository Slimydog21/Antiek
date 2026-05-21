"""Cross-document edge query layer (SPR-07 M1).

The wrestle-evolution gutter-pill surface (SPR-07) shows 1–3 connected
passages to the user when they highlight text. This module owns the
substrate-side query that picks those 3 candidates.

The score fusion (vector similarity + user-asserted edges + citation
edges) is documented in ``SCORING.md``. The single public entry point
is :func:`get_cross_doc_links` — every other helper in this package is
internal.
"""

from .query import (
    CrossDocCandidate,
    CrossDocLink,
    Highlight,
    SCORING_WEIGHTS,
    get_cross_doc_links,
)

__all__ = [
    "CrossDocCandidate",
    "CrossDocLink",
    "Highlight",
    "SCORING_WEIGHTS",
    "get_cross_doc_links",
]
