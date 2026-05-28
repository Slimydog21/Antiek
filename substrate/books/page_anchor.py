"""Map a chunk's ``section_path`` back to a reader page index (Read SPR-08).

The book reader paginates the served markdown on ``## Page N`` markers
(``acquisition/books/reader.py`` → ``apps/reading/src/modes/Reading/paginate.ts``).
The chunker (``processing/chunking/chunker.py``) is heading-aware: a
``## Page N`` line becomes that chunk's ``section`` (== ``Page N``), which is
persisted as ``chunks.section_path``. So a chunk that sits directly under a
page marker carries a RESOLVABLE page anchor in its ``section_path``.

WHY THIS IS APPROXIMATE — stated, never hidden (rigor #1). The mapping is
EXACT only when ``section_path`` is literally ``Page N``. It is UNRESOLVABLE
(returns ``None``) when:

  • a sub-heading inside the page (a promoted all-caps line → ``# heading``,
    or a ``# Chapter`` title) overwrote the section AFTER the page marker, so
    the chunk's nearest heading is the chapter, not the page; or
  • the chunk spans a page boundary (the chunker carries the section forward,
    not the page marker); or
  • ``section_path`` is NULL (a snippet / unpaginated body).

A consumer that gets ``None`` must surface an HONEST "page not resolved" state
(jump to the book, not a fabricated page) — never present an unresolved anchor
as an exact page. The single source of truth for the ``Page N`` ⇄ page_index
coordinate is the same one the reader uses: page index = N − 1 (0-based).
"""

from __future__ import annotations

import re
from typing import Optional

# ``## Page N`` → chunker section "Page N". Tolerant of surrounding whitespace
# and case, matching the reader's PAGE_MARKER (paginate.ts) one-for-one.
_PAGE_SECTION_RE = re.compile(r"^\s*page\s+(\d+)\s*$", re.IGNORECASE)


def page_index_from_section_path(section_path: Optional[str]) -> Optional[int]:
    """The 0-based reader page index a chunk anchors to, or ``None`` when the
    chunk's ``section_path`` does not resolve to a page marker.

    EXACT for ``"Page N"`` (→ ``N - 1``); ``None`` for a chapter/section title,
    a NULL section, or any non-page heading. ``None`` is the honest
    "approximate / unresolved" signal — the caller must NOT invent a page.
    """
    if not section_path:
        return None
    m = _PAGE_SECTION_RE.match(section_path)
    if not m:
        return None
    n = int(m.group(1))
    # Page numbers are 1-based in the marker; the reader locator is 0-based.
    # A degenerate "Page 0" (shouldn't occur — markers are page_index + 1)
    # clamps to the first page rather than going negative.
    return max(0, n - 1)
