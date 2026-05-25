"""PDF reader — page extraction + light markdown formatting.

Uses ``pypdf`` (optional ``[pdf]`` extra). Extracts per-page text,
joins consecutive pages into a markdown document with synthetic
section headers (``## Page N``) so the chunker has anchor metadata.
Optionally promotes runs of all-caps lines to ``# Heading`` so the
text isn't a single 200-page blob.

Metadata (title + author) is pulled from the PDF info dict when
present.

Not a general-purpose PDF parser. Sufficient for the operator's
"drop a PDF in and start wrestling" path; complex layouts (multi-
column papers, scanned books) should go through a dedicated OCR
pipeline downstream. The cleanly-extractable-text gate is the
threshold for whether this module's output is useful — callers can
inspect ``ReadResult.word_count`` to decide.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

try:
    from pypdf import PdfReader  # type: ignore[import-not-found]
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "acquisition.books.reader requires pypdf. "
        "Run `pip install -e '.[pdf]'` to install it."
    ) from e


@dataclass(frozen=True)
class PdfPage:
    """One extracted page."""

    page_index: int  # 0-based
    text: str
    word_count: int


@dataclass(frozen=True)
class TocEntry:
    """One table-of-contents entry. ``page_index`` is the 0-based page
    the bookmark targets — the locator scheme is "PDF page index", the
    same coordinate the ``## Page N`` markdown anchors use (N is
    ``page_index + 1``). ``level`` is the nesting depth (0 = top-level
    chapter). ``page_index`` is ``None`` when pypdf can't resolve the
    destination to a page (malformed outline) — surfaced rather than
    dropped, per intellectual honesty (rigor #1)."""

    title: str
    page_index: Optional[int]
    level: int


@dataclass(frozen=True)
class ReadResult:
    """What ``read_pdf`` returns. ``markdown`` is the chunker-ready
    concatenation; ``pages`` lets advanced callers inspect per-page
    extraction quality; ``toc`` is the flattened bookmark outline (empty
    when the PDF carries no outline — most scanned/auto-generated PDFs
    don't)."""

    title: Optional[str]
    author: Optional[str]
    page_count: int
    word_count: int
    markdown: str
    pages: List[PdfPage] = field(default_factory=list)
    toc: List[TocEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Page-text cleanup
# ---------------------------------------------------------------------------


_HEADING_LIKE_RE = re.compile(r"^[A-Z0-9][A-Z0-9 .\-]{3,}$")
# Soft-wrap line endings: "word-\nrest" → "wordrest". Pypdf preserves
# hyphenation at line breaks; the chunker prefers re-joined words.
_SOFT_WRAP_RE = re.compile(r"([a-z])-\n([a-z])")
_MULTI_WS_RE = re.compile(r"[ \t]+")


def _clean_page_text(text: str) -> str:
    """Light-touch normalization. Joins soft-wrapped hyphenations,
    collapses runs of spaces, strips trailing whitespace per line."""
    if not text:
        return ""
    text = _SOFT_WRAP_RE.sub(r"\1\2", text)
    cleaned_lines: List[str] = []
    for raw in text.splitlines():
        line = _MULTI_WS_RE.sub(" ", raw).rstrip()
        cleaned_lines.append(line)
    # Trim trailing/leading blank lines but keep internal paragraph breaks.
    while cleaned_lines and not cleaned_lines[0].strip():
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()
    return "\n".join(cleaned_lines)


def _promote_headings(text: str) -> str:
    """Lift all-caps lines to ``# heading`` so the chunker can split
    on them. Conservative: only promotes lines that are 4-60 chars,
    all uppercase/punct, and not surrounded by other non-blank
    content (i.e. they look like headings, not shout-style emphasis
    mid-paragraph)."""
    lines = text.splitlines()
    out: List[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped
            and 4 <= len(stripped) <= 60
            and _HEADING_LIKE_RE.match(stripped)
            and (i == 0 or not lines[i - 1].strip())
            and (i == len(lines) - 1 or not lines[i + 1].strip())
        ):
            out.append(f"# {stripped.title()}")
        else:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


def _extract_pages(reader: PdfReader) -> List[PdfPage]:
    pages: List[PdfPage] = []
    for i, page in enumerate(reader.pages):
        try:
            raw = page.extract_text() or ""
        except Exception:  # pypdf can raise on corrupt page; skip cleanly
            raw = ""
        cleaned = _clean_page_text(raw)
        pages.append(
            PdfPage(
                page_index=i, text=cleaned,
                word_count=len(cleaned.split()),
            ),
        )
    return pages


def _extract_outline(reader: PdfReader) -> List[TocEntry]:
    """Flatten pypdf's nested bookmark outline into ordered TocEntry rows.

    pypdf exposes ``reader.outline`` as a tree: a list whose items are
    either ``Destination`` objects (a bookmark) or nested lists (the
    children of the immediately-preceding bookmark). We walk it depth-
    first, recording the nesting ``level``, and resolve each
    destination's page via ``get_destination_page_number``.

    Defensive throughout: PDFs lie. A missing/locked outline yields an
    empty list; an unresolvable destination yields an entry with
    ``page_index=None`` rather than crashing the whole read. This is the
    "no new parser invented" path — we read the structure the PDF already
    declares, we don't infer one.
    """
    try:
        raw = reader.outline  # type: ignore[attr-defined]
    except Exception:
        return []
    if not raw:
        return []

    entries: List[TocEntry] = []

    def _walk(node: object, level: int) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item, level)
            return
        title = getattr(node, "title", None)
        if not title:
            return
        page_index: Optional[int]
        try:
            page_index = reader.get_destination_page_number(node)  # type: ignore[arg-type]
        except Exception:
            page_index = None
        entries.append(
            TocEntry(title=str(title).strip(), page_index=page_index, level=level)
        )

    # Top level is a flat list; a nested list deepens the level by one and
    # belongs to the bookmark that preceded it.
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, list):
                _walk(item, 1)
            else:
                _walk(item, 0)
    return entries


def _metadata_field(meta: object, key: str) -> Optional[str]:
    """pypdf returns a dict-ish object; values may have a ``/`` prefix
    or come as ``IndirectObject``. Coerce to a plain string when we
    can; None when missing."""
    if meta is None:
        return None
    try:
        val = meta.get(key)  # type: ignore[union-attr]
    except Exception:
        return None
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _join_pages_to_markdown(
    pages: Sequence[PdfPage],
    *,
    promote_headings: bool,
) -> str:
    """Concatenate pages with ``## Page N`` markers so the chunker
    sees structural anchors instead of one blob."""
    parts: List[str] = []
    for p in pages:
        if not p.text.strip():
            continue
        body = _promote_headings(p.text) if promote_headings else p.text
        parts.append(f"## Page {p.page_index + 1}")
        parts.append("")
        parts.append(body)
        parts.append("")
    return "\n".join(parts).strip()


def read_pdf(
    source: bytes | io.IOBase | str,
    *,
    promote_headings: bool = True,
) -> ReadResult:
    """Read a PDF from bytes, file-like, or path string. Returns
    ``ReadResult`` with the per-page extraction + the chunker-ready
    markdown joined view."""
    if isinstance(source, bytes):
        reader = PdfReader(io.BytesIO(source))
    elif isinstance(source, (str,)):
        reader = PdfReader(source)
    else:
        reader = PdfReader(source)

    meta = reader.metadata
    title = _metadata_field(meta, "/Title")
    author = _metadata_field(meta, "/Author")

    pages = _extract_pages(reader)
    toc = _extract_outline(reader)
    markdown_parts: List[str] = []
    if title:
        markdown_parts.append(f"# {title}")
        markdown_parts.append("")
    if author:
        markdown_parts.append(f"_by {author}_")
        markdown_parts.append("")
    body = _join_pages_to_markdown(pages, promote_headings=promote_headings)
    if body:
        markdown_parts.append(body)
    full = "\n".join(markdown_parts).strip()

    return ReadResult(
        title=title,
        author=author,
        page_count=len(pages),
        word_count=sum(p.word_count for p in pages),
        markdown=full,
        pages=pages,
        toc=toc,
    )
