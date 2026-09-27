"""Read the heading outline of a final, bounded reader-HTML body."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from xml.dom.minidom import CDATASection, Document, DocumentFragment, Element, Node, Text

from substrate.books.model import TocItem

# ECMAScript String.prototype.trim whitespace. U+0085 is intentionally absent;
# U+FEFF is intentionally present to match the browser reader.
_JS_TRIM_CHARS = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
    "\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


@dataclass(frozen=True)
class HtmlOutline:
    """Existing TOC locators and the count of browser-visible HTML windows."""

    toc: tuple[TocItem, ...]
    page_count: int

    @property
    def first_heading(self) -> str | None:
        """Return the first visible heading title, if the body has one."""
        return self.toc[0].title if self.toc else None


def _js_trim(value: str) -> str:
    """Trim exactly the edge code points trimmed by JavaScript ``String.trim``."""
    return value.strip(_JS_TRIM_CHARS)


def _text_content(node: Node) -> str:
    """Return DOM textContent semantics without including comment data."""
    parts: list[str] = []
    pending = [node]
    while pending:
        current = pending.pop()
        if isinstance(current, (Text, CDATASection)):
            parts.append(current.data)
        elif isinstance(current, (Element, Document, DocumentFragment)):
            pending.extend(reversed(current.childNodes))
    return "".join(parts)


def _body_headings(body: Node) -> list[tuple[str, int]]:
    headings: list[tuple[str, int]] = []
    pending = list(reversed(body.childNodes))
    while pending:
        node = pending.pop()
        if not isinstance(node, Element):
            continue
        tag = node.tagName.lower()
        if tag in _HEADING_TAGS:
            title = _js_trim(_text_content(node))
            if title:
                headings.append((title, int(tag[1])))
        pending.extend(reversed(node.childNodes))
    return headings


def _parse_html5_document(final_html: str) -> Document:
    """Parse in HTML document mode and validate the untyped library boundary."""
    parse = import_module("html5lib").parse
    parsed_document: object = parse(final_html, treebuilder="dom")
    if not isinstance(parsed_document, Document):
        raise TypeError("html5lib DOM builder did not return a minidom Document")
    return parsed_document


def outline_html_document(final_html: str) -> HtmlOutline:
    """Derive TOC and heading-window count from final HTML without rewriting it.

    Parsing follows the browser's HTML document mode (`DOMParser` with
    `text/html`), then considers only h1–h6 elements below `body` in DOM order.
    TOC levels are relative to the shallowest nonempty heading. The caller is
    responsible for supplying the final bounded body produced by the trusted
    reader-HTML transformation.
    """
    document = _parse_html5_document(final_html)
    bodies = document.getElementsByTagName("body")
    if not bodies:
        raise ValueError("HTML5 document parser returned no body element")
    body = bodies[0]
    headings = _body_headings(body)
    if not headings:
        return HtmlOutline(toc=(), page_count=1 if _js_trim(final_html) else 0)

    shallowest = min(level for _, level in headings)
    toc = tuple(
        TocItem(title=title, page_index=index, level=level - shallowest)
        for index, (title, level) in enumerate(headings)
    )
    return HtmlOutline(toc=toc, page_count=len(toc))


def choose_initial_upload_title(
    *,
    explicit_title: str | None,
    first_heading: str | None,
    filename_stem: str | None,
    document_id: str,
) -> str:
    """Choose the first nonblank title candidate without changing stored rows."""
    for candidate in (explicit_title, first_heading, filename_stem, document_id):
        if candidate is not None:
            title = _js_trim(candidate)
            if title:
                return title
    return _js_trim(document_id)
