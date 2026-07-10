"""epub → Antiek-HTML conversion (SPR-02 — the engine the legacy stubs only
receipted).

``convert_epub_to_antiek_html`` takes a legally-held LOCAL ``.epub`` and
produces a :class:`ConvertedBook`:

- ``html`` — the canonical Antiek-HTML body: one ``<section
  id="antiek-chapter-N">`` per spine chapter, whose content has passed the
  SPR-01 allowlist sanitizer (``substrate.books.html_sanitizer``). The
  converter CANNOT emit executable HTML even when the source epub embeds
  scripts/handlers — sanitization is structural, not optional, and the
  assembled document is passed through the sanitizer once more as a belt, so
  ``html`` is a sanitizer fixed point.
- ``markdown`` — a deterministic text projection of the same content, in the
  heading-aware shape ``processing.chunking.chunker.chunk_markdown`` consumes.
  This is the SAME chunker the native books path
  (``acquisition/books/adapter.ingest_pdf``) feeds, so an imported book
  chunks/grounds identically to a natively-published one (proven in
  ``tests/test_book_import_convert.py``).
- ``toc`` — headings (h1–h3) with their chapter index and anchor, in the
  shape ``substrate.books.model.TocItem`` consumes at publish time.

Honesty about fidelity: this extracts the readable, searchable content — the
structure and text — NOT the original typography, fonts, or pixel layout.
That is by design: the target is HTML-everywhere reading and talk-to-book
grounding, not a facsimile. Lost layout is not a bug.

Determinism: same input bytes → byte-identical ``html`` and ``markdown``
(asserted in tests). Downstream content-addressed document/chunk ids depend
on this.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from substrate.books.html_sanitizer import SANITIZER_VERSION, sanitize_book_html

from .epub import EpubLimits, EpubSource, read_epub
from .errors import NoTextContentError

CONVERTER_VERSION = "book-import-epub/1.0.0"

_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
# chunk_markdown's heading regex recognizes # through #### only; deeper
# headings are projected at the cap so they still open a section.
_MARKDOWN_HEADING_CAP = 4

# Tags that open a markdown block in the text projection. blockquote is NOT
# here — it nests block children (<blockquote><p>…) and is tracked as a depth
# so quoted paragraphs keep their "> " prefix.
_BLOCK_TAGS = frozenset({
    "p", "li", "pre", "figcaption", "caption",
    "dt", "dd", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
})


@dataclass(frozen=True)
class TocHeading:
    """One collected heading: its text, level, owning chapter (0-based), and
    the sanitized ``id`` anchor when the source carried one."""

    title: str
    level: int
    chapter_index: int
    anchor: str | None


@dataclass(frozen=True)
class ConvertedBook:
    """The conversion result handed to ``publish_converted_book``. ``html``
    is ALREADY sanitized (a fixed point of ``sanitize_book_html``);
    ``markdown`` is the chunker-facing text projection of the same content."""

    html: str
    markdown: str
    title: str | None
    author: str | None
    chapter_count: int
    toc: tuple[TocHeading, ...]
    source_format: str
    converter_version: str
    sanitizer_version: str


class _TocCollector(HTMLParser):
    """Collect h1–h3 headings (text + optional id) from SANITIZED chapter
    HTML. Runs over sanitizer output only, so the tag soup is already tame."""

    def __init__(self, chapter_index: int) -> None:
        super().__init__(convert_charrefs=True)
        self.chapter_index = chapter_index
        self.headings: list[TocHeading] = []
        self._level: int | None = None
        self._anchor: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        level = _HEADING_TAGS.get(tag)
        if level is None or level > 3 or self._level is not None:
            return
        self._level = level
        self._anchor = next((v for k, v in attrs if k == "id" and v), None)
        self._text = []

    def handle_endtag(self, tag: str) -> None:
        if self._level is None or _HEADING_TAGS.get(tag) != self._level:
            return
        title = " ".join("".join(self._text).split())
        if title:
            self.headings.append(
                TocHeading(
                    title=title,
                    level=self._level,
                    chapter_index=self.chapter_index,
                    anchor=self._anchor,
                )
            )
        self._level = None
        self._anchor = None
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._level is not None:
            self._text.append(data)


class _MarkdownProjector(HTMLParser):
    """Project SANITIZED chapter HTML to the heading-aware markdown shape
    ``chunk_markdown`` consumes. Inline markup flattens to text; block tags
    delimit blocks; headings become ``#``-prefixed lines. Deterministic."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._blocks: list[str] = []
        self._current: list[str] = []
        self._heading_level: int | None = None
        self._block_tag: str | None = None
        self._in_pre = False
        self._quote_depth = 0

    def _flush(self) -> None:
        raw = "".join(self._current)
        self._current = []
        if self._in_pre or self._block_tag == "pre":
            text = raw.strip("\n")
        else:
            text = " ".join(raw.split())
        if not text:
            return
        if self._heading_level is not None:
            prefix = "#" * min(self._heading_level, _MARKDOWN_HEADING_CAP)
            self._blocks.append(f"{prefix} {text}")
        elif self._block_tag == "li":
            self._blocks.append(f"- {text}")
        elif self._quote_depth > 0:
            self._blocks.append(f"> {text}")
        else:
            self._blocks.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "blockquote":
            self._flush()
            self._quote_depth += 1
        elif tag in _BLOCK_TAGS:
            self._flush()
            self._block_tag = tag
            self._heading_level = _HEADING_TAGS.get(tag)
            if tag == "pre":
                self._in_pre = True
        elif tag == "br":
            self._current.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "blockquote":
            self._flush()
            if self._quote_depth:
                self._quote_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._flush()
            self._block_tag = None
            self._heading_level = None
            if tag == "pre":
                self._in_pre = False

    def handle_data(self, data: str) -> None:
        self._current.append(data)

    def result(self) -> str:
        self._flush()
        return "\n\n".join(self._blocks)


def _project_markdown(sanitized_html: str) -> str:
    projector = _MarkdownProjector()
    projector.feed(sanitized_html)
    projector.close()
    return projector.result()


def _collect_toc(sanitized_html: str, chapter_index: int) -> list[TocHeading]:
    collector = _TocCollector(chapter_index)
    collector.feed(sanitized_html)
    collector.close()
    return collector.headings


def convert_epub_to_antiek_html(
    source: EpubSource, *, limits: EpubLimits | None = None
) -> ConvertedBook:
    """Convert a legally-held local epub to sanitized Antiek HTML + the
    chunker-facing markdown projection.

    Raises the typed :mod:`substrate.book_import.errors` vocabulary on any
    hostile/unreadable input; a book with no readable text raises
    ``NoTextContentError`` rather than converting to a hollow shell.
    """
    book = read_epub(source, limits=limits)

    sections: list[str] = []
    markdown_parts: list[str] = []
    toc: list[TocHeading] = []
    for index, chapter in enumerate(book.chapters):
        inner = sanitize_book_html(chapter.xhtml).strip()
        sections.append(
            f'<section id="antiek-chapter-{index + 1}">\n{inner}\n</section>'
        )
        chapter_markdown = _project_markdown(inner)
        if chapter_markdown:
            markdown_parts.append(chapter_markdown)
        toc.extend(_collect_toc(inner, index))

    # Belt: the assembled document goes through the sanitizer once more, so
    # ConvertedBook.html is a sanitizer FIXED POINT regardless of how the
    # wrapper markup above evolves. (sanitize is idempotent, so this is a
    # no-op today — the guarantee is what matters.)
    html = sanitize_book_html("\n".join(sections))
    markdown = "\n\n".join(markdown_parts)

    if not markdown.strip():
        raise NoTextContentError(
            "epub converted to no readable text — refusing to publish a hollow book"
        )

    return ConvertedBook(
        html=html,
        markdown=markdown,
        title=book.title,
        author=book.author,
        chapter_count=len(book.chapters),
        toc=tuple(toc),
        source_format="epub",
        converter_version=CONVERTER_VERSION,
        sanitizer_version=SANITIZER_VERSION,
    )


__all__ = [
    "CONVERTER_VERSION",
    "ConvertedBook",
    "TocHeading",
    "convert_epub_to_antiek_html",
]
