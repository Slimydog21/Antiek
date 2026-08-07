"""HTML → markdown extraction.

Two stages:

1. **Main-content isolation** (BeautifulSoup). Drop ``<script>``,
   ``<style>``, ``<nav>``, ``<header>``, ``<footer>``, ``<aside>``,
   and elements with role=banner/navigation/complementary. Prefer
   the first of ``<article>`` / ``<main>`` / ``role=main`` / the
   biggest ``<div>`` as the root; fall back to ``<body>``.

2. **Markdown rendering** (``html2text``). ASCII-only output, link
   inlining, no body width wrapping. Code blocks preserved via
   ``<pre>`` → fenced.

Title resolution order: ``<meta property=og:title>`` →
``<title>`` → first ``<h1>``. Author resolution: ``<meta name=author>``
→ ``<meta property=article:author>`` → schema.org/Person markup.
Both fields are best-effort; ``None`` is a valid result.

This is intentionally a lightweight extractor, not a full readability
port. Pages where this misses badly (heavy JS / paywall stubs) should
go through ``acquisition/books/`` after rendering to PDF instead.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from bs4 import BeautifulSoup, Tag  # type: ignore[import-not-found]
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "acquisition.urls.extract requires beautifulsoup4. "
        "Run `pip install -e '.[urls]'` to install it."
    ) from e

try:
    import html2text  # type: ignore[import-not-found]
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "acquisition.urls.extract requires html2text. "
        "Run `pip install -e '.[urls]'` to install it."
    ) from e


@dataclass(frozen=True)
class MarkdownDoc:
    """Extracted document. ``markdown`` is the full body; ``title``
    and ``author`` are best-effort. ``word_count`` is the markdown
    body's whitespace-split count — a coarse sanity check before
    chunking (very low → extractor likely missed the article)."""

    title: str | None
    author: str | None
    markdown: str
    word_count: int
    final_url: str | None = None
    # The ISOLATED main-content HTML (chrome stripped, main root serialized).
    # Computed by the extractor anyway (the root Tag), carried so the ingest
    # path can feed the reader-HTML sidecar — sanitize-on-write happens in
    # substrate.reader_html.store, never here (doc→HTML S1).
    main_html: str = ""


# Tags to strip wholesale — UI chrome that pollutes the article body.
_STRIP_TAGS = {
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "iframe", "form", "button", "svg",
}
_STRIP_ROLES = {"banner", "navigation", "complementary", "search"}


def _strip_chrome(soup: BeautifulSoup) -> None:
    """Remove UI chrome in place. We do this BEFORE main-content
    selection so the biggest-div heuristic isn't tricked by a giant
    sidebar."""
    for tag in soup.find_all(list(_STRIP_TAGS)):
        tag.decompose()
    for el in soup.find_all(role=True):
        if el.get("role") in _STRIP_ROLES:
            el.decompose()


def _pick_main(soup: BeautifulSoup) -> Tag:
    """Pick the best root for article content. The order here
    encodes our prior on which signals are most reliable."""
    article = soup.find("article")
    if article and len(article.get_text(strip=True)) > 100:
        return article
    main = soup.find("main")
    if main and len(main.get_text(strip=True)) > 100:
        return main
    role_main = soup.find(role="main")
    if role_main and len(role_main.get_text(strip=True)) > 100:
        return role_main

    # Fallback: pick the <div> whose stripped text is largest.
    # Bias toward divs with content-bearing class names if scores tie.
    best = None
    best_len = 0
    for div in soup.find_all("div"):
        txt = div.get_text(strip=True)
        if len(txt) > best_len:
            best = div
            best_len = len(txt)
    if best is not None and best_len >= 100:
        return best
    body = soup.body
    if body is None:
        return soup
    return body


def _resolve_title(soup: BeautifulSoup) -> str | None:
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        content = og["content"]
        return content.strip() if isinstance(content, str) else None
    title = soup.find("title")
    if title and title.get_text(strip=True):
        text = title.get_text(strip=True)
        return text if isinstance(text, str) else None
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        text = h1.get_text(strip=True)
        return text if isinstance(text, str) else None
    return None


def _resolve_author(soup: BeautifulSoup) -> str | None:
    for meta in (
        soup.find("meta", attrs={"name": "author"}),
        soup.find("meta", property="article:author"),
        soup.find("meta", attrs={"name": "byl"}),  # NYT
    ):
        if meta and meta.get("content"):
            content = meta["content"]
            return content.strip() if isinstance(content, str) else None
    sch = soup.find(itemprop="author")
    if sch:
        name = sch.find(itemprop="name")
        if name and name.get_text(strip=True):
            text = name.get_text(strip=True)
            return text if isinstance(text, str) else None
        txt = sch.get_text(strip=True)
        if txt:
            return txt if isinstance(txt, str) else None
    return None


def _make_markdown_writer(base_url: str | None) -> html2text.HTML2Text:
    h = html2text.HTML2Text(baseurl=base_url or "")
    h.body_width = 0  # no hard-wrap; chunker prefers long lines
    h.ignore_images = True
    h.ignore_emphasis = False
    h.unicode_snob = True
    h.skip_internal_links = True
    h.protect_links = True
    return h


def html_to_markdown(
    html: bytes | str,
    *,
    base_url: str | None = None,
) -> MarkdownDoc:
    """Extract main content + render to markdown. ``html`` may be
    raw bytes (assumed utf-8) or a string."""
    if isinstance(html, bytes):
        try:
            html_str = html.decode("utf-8")
        except UnicodeDecodeError:
            # Fall back to latin-1 — preserves every byte rather than
            # losing characters; the extractor's regex layer can cope.
            html_str = html.decode("latin-1", errors="replace")
    else:
        html_str = html

    soup = BeautifulSoup(html_str, "html.parser")
    title = _resolve_title(soup)
    author = _resolve_author(soup)
    _strip_chrome(soup)
    root = _pick_main(soup)

    writer = _make_markdown_writer(base_url)
    body_md = writer.handle(str(root)).strip()

    # Prepend a leading title line so the chunker has the heading
    # anchor (it splits on # / ## / etc.). Authors ride along when
    # known — keeps provenance in the chunk text.
    header_lines: list[str] = []
    if title:
        header_lines.append(f"# {title}")
        header_lines.append("")
    if author:
        header_lines.append(f"_by {author}_")
        header_lines.append("")
    full = ("\n".join(header_lines) + body_md).strip()
    return MarkdownDoc(
        title=title,
        author=author,
        markdown=full,
        word_count=len(full.split()),
        final_url=base_url,
        main_html=str(root),
    )
