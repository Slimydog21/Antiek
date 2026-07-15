"""Pure library catalog page builder (filter / search / paginate).

Separated from the FastAPI route so catalog honesty is unit-testable without
DuckDB or ``create_app``. Body text must never appear on catalog summaries —
callers pass already-metadata ``BookSummary`` rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from interfaces.research.api.books import BookSummary

LibraryFilter = Literal["servable", "gated", "all"]

# Fields that must never appear on a catalog summary payload (§9.0).
_FORBIDDEN_BODY_KEYS = frozenset(
    {
        "raw_text",
        "full_text",
        "body",
        "body_text",
        "content",
        "served_body",
        "text",
    }
)


class LibraryPage(BaseModel):
    """One page of the catalog (metadata only — never a body)."""

    works: list[BookSummary]
    total: int
    page: int
    page_size: int


def matches_search(summary: BookSummary, needle: str) -> bool:
    """Case-insensitive substring over title + author only (never body)."""
    if not needle:
        return True
    hay = " ".join(part.lower() for part in (summary.title, summary.author) if part)
    return needle.lower() in hay


def apply_servability_filter(
    summaries: Sequence[BookSummary],
    filt: LibraryFilter,
) -> list[BookSummary]:
    """Filter summaries by servable / gated / all."""
    rows = list(summaries)
    if filt == "servable":
        return [s for s in rows if s.servable_full_text]
    if filt == "gated":
        return [s for s in rows if not s.servable_full_text]
    return rows


def build_library_page(
    summaries: Sequence[BookSummary],
    *,
    filt: LibraryFilter = "all",
    search: str = "",
    page: int = 1,
    page_size: int = 20,
) -> LibraryPage:
    """Filter, search, then paginate. ``total`` is post-filter/search count."""
    if page < 1:
        raise ValueError("page must be >= 1")
    if page_size < 1 or page_size > 200:
        raise ValueError("page_size must be in 1..200")

    filtered = apply_servability_filter(summaries, filt)
    matched = [s for s in filtered if matches_search(s, search)]
    total = len(matched)
    start = (page - 1) * page_size
    works = matched[start : start + page_size]
    return LibraryPage(works=works, total=total, page=page, page_size=page_size)


def summary_payload_has_no_body(summary: BookSummary) -> bool:
    """True when model dump has no forbidden body-like keys."""
    data = summary.model_dump()
    return not any(k in data for k in _FORBIDDEN_BODY_KEYS)


__all__ = [
    "LibraryFilter",
    "LibraryPage",
    "apply_servability_filter",
    "build_library_page",
    "matches_search",
    "summary_payload_has_no_body",
]
