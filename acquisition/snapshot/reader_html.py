"""Sanitized HTML reader snapshot after URL/HTML ingest (SPR-AHT-04).

``markdown_to_safe_html`` is the first thing that touches a PDF, docx or epub
after conversion, so whatever structure it drops is gone before the reader, the
style wheel or any projection ever sees the document. It therefore renders a
real GFM subset — headings, lists, tables, links, images, emphasis, code,
blockquotes, rules — rather than headings-and-paragraphs with everything else
escaped into literal text.

The renderer is escape-first and stays that way. Every text node passes through
:func:`html.escape` at the moment it is emitted and structural tags are written
around it, so no byte of the source is ever copied out verbatim and the output
remains a safe input to ``substrate.books.html_sanitizer``, which is the actual
trust floor. The tag vocabulary below is a subset of that module's
``ALLOWED_TAGS``; anything it would strip is not worth emitting.

Parsing is hand-rolled on the stdlib. The repo declares no markdown dependency
and the in-tree precedent for this kind of work is the sanitizer's own
``HTMLParser`` pass, so a line-oriented block scanner plus one inline regex is
the right size for the job.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

_SCRIPT_RE = re.compile(r"<script[\s\S]*?</script>", re.IGNORECASE)
_STYLE_RE = re.compile(r"<style[\s\S]*?</style>", re.IGNORECASE)


def sanitize_html_fragment(raw: str, *, max_chars: int = 200_000) -> str:
    return _STYLE_RE.sub("", _SCRIPT_RE.sub("", raw[:max_chars]))


# --- GFM subset renderer ------------------------------------------------------

# Guard against pathological nesting (a file of nothing but "> > > > ...").
_MAX_NEST = 8

_ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*#*[ \t]*$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*[^`]*$")
_HR_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_QUOTE_RE = re.compile(r"^ {0,3}>[ \t]?(.*)$")
_BULLET_RE = re.compile(r"^([ \t]*)([-+*])[ \t]+(.*)$")
_ORDERED_RE = re.compile(r"^([ \t]*)(\d{1,9})([.)])[ \t]+(.*)$")
_DELIM_CELL_RE = re.compile(r":?-+:?\Z")

# One pass over a line finds the next inline construct. Order matters: the
# longer opener of an ambiguous pair (``***`` before ``**`` before ``*``) has to
# come first, and code spans come early so markers inside them stay literal.
_INLINE_RE = re.compile(
    r"(?P<esc>\\(?P<esc_ch>[\\`*_{}\[\]()#+\-.!>~|]))"
    r"|(?P<code>(?P<tick>`+)(?P<code_body>.+?)(?P=tick))"
    r"|(?P<img>!\[(?P<img_alt>[^\]]*)\]\((?P<img_src>[^()\s]*)(?:[ \t]+\"[^\"]*\")?\))"
    r"|(?P<link>\[(?P<link_text>[^\]]*)\]\((?P<link_href>[^()\s]*)(?:[ \t]+\"[^\"]*\")?\))"
    r"|(?P<auto><(?P<auto_url>https?://[^<>\s]+)>)"
    r"|(?P<both>\*\*\*(?P<both_body>[^\s*](?:.*?[^\s*])?)\*\*\*)"
    r"|(?P<both2>(?<![A-Za-z0-9])___(?P<both2_body>[^\s_](?:.*?[^\s_])?)___(?![A-Za-z0-9]))"
    r"|(?P<strong>\*\*(?P<strong_body>[^\s*](?:.*?[^\s*])?)\*\*)"
    r"|(?P<strong2>(?<![A-Za-z0-9])__(?P<strong2_body>[^\s_](?:.*?[^\s_])?)__(?![A-Za-z0-9]))"
    r"|(?P<strike>~~(?P<strike_body>[^\s~](?:.*?[^\s~])?)~~)"
    r"|(?P<em>\*(?P<em_body>[^\s*](?:.*?[^\s*])?)\*)"
    r"|(?P<em2>(?<![A-Za-z0-9])_(?P<em2_body>[^\s_](?:.*?[^\s_])?)_(?![A-Za-z0-9]))"
)


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _attr(value: str) -> str:
    return html.escape(value, quote=True)


def _indent_width(prefix: str) -> int:
    width = 0
    for ch in prefix:
        width += 4 - (width % 4) if ch == "\t" else 1
    return width


def _leading_indent(line: str) -> int:
    return _indent_width(line[: len(line) - len(line.lstrip(" \t"))])


def _strip_indent(line: str, amount: int) -> str:
    removed = 0
    out = line
    while removed < amount and out[:1] in (" ", "\t"):
        removed += 4 - (removed % 4) if out[0] == "\t" else 1
        out = out[1:]
    return out


def _render_inline(text: str, depth: int = 0) -> str:
    """Escape ``text`` and wrap its inline markdown constructs in tags."""
    if depth >= _MAX_NEST:
        return _esc(text)
    out: list[str] = []
    pos = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() < pos:
            continue
        out.append(_esc(text[pos : match.start()]))
        pos = match.end()
        if match.group("esc") is not None:
            out.append(_esc(match.group("esc_ch")))
        elif match.group("code") is not None:
            out.append(f"<code>{_esc(match.group('code_body'))}</code>")
        elif match.group("img") is not None:
            src = match.group("img_src")
            alt = match.group("img_alt")
            attrs = f' src="{_attr(src)}"' if src else ""
            attrs += f' alt="{_attr(alt)}"' if alt else ""
            out.append(f"<img{attrs} />")
        elif match.group("link") is not None:
            href = match.group("link_href")
            inner = _render_inline(match.group("link_text"), depth + 1)
            open_tag = f'<a href="{_attr(href)}">' if href else "<a>"
            out.append(f"{open_tag}{inner}</a>")
        elif match.group("auto") is not None:
            url = match.group("auto_url")
            out.append(f'<a href="{_attr(url)}">{_esc(url)}</a>')
        elif match.group("both") is not None:
            body = _render_inline(match.group("both_body"), depth + 1)
            out.append(f"<em><strong>{body}</strong></em>")
        elif match.group("both2") is not None:
            body = _render_inline(match.group("both2_body"), depth + 1)
            out.append(f"<em><strong>{body}</strong></em>")
        elif match.group("strong") is not None:
            body = _render_inline(match.group("strong_body"), depth + 1)
            out.append(f"<strong>{body}</strong>")
        elif match.group("strong2") is not None:
            body = _render_inline(match.group("strong2_body"), depth + 1)
            out.append(f"<strong>{body}</strong>")
        elif match.group("strike") is not None:
            body = _render_inline(match.group("strike_body"), depth + 1)
            out.append(f"<s>{body}</s>")
        elif match.group("em") is not None:
            body = _render_inline(match.group("em_body"), depth + 1)
            out.append(f"<em>{body}</em>")
        elif match.group("em2") is not None:
            body = _render_inline(match.group("em2_body"), depth + 1)
            out.append(f"<em>{body}</em>")
    out.append(_esc(text[pos:]))
    return "".join(out)


def _split_cells(row: str) -> list[str]:
    r"""Split one pipe-table row, honouring ``\|`` escapes."""
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells: list[str] = []
    buf: list[str] = []
    index = 0
    while index < len(body):
        ch = body[index]
        if ch == "\\" and body[index + 1 : index + 2] == "|":
            buf.append("|")
            index += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            index += 1
            continue
        buf.append(ch)
        index += 1
    cells.append("".join(buf).strip())
    return cells


def _table_header(lines: list[str], index: int) -> list[str] | None:
    """Header cells iff line ``index`` opens a GFM pipe table, else None."""
    if index + 1 >= len(lines):
        return None
    header, delim = lines[index], lines[index + 1]
    if "|" not in header or "-" not in delim:
        return None
    header_cells = _split_cells(header)
    delim_cells = _split_cells(delim)
    if not header_cells or len(header_cells) != len(delim_cells):
        return None
    if not all(_DELIM_CELL_RE.match(cell) for cell in delim_cells):
        return None
    return header_cells


def _starts_block(lines: list[str], index: int) -> bool:
    """Whether line ``index`` interrupts a run of paragraph text.

    Stricter than the block dispatch in :func:`_render_blocks`: only a ``1.``
    ordered item and a non-empty bullet may break a paragraph, so a sentence
    wrapping onto ``2026. That year...`` stays prose.
    """
    line = lines[index]
    if _FENCE_RE.match(line) or _ATX_RE.match(line) or _HR_RE.match(line):
        return True
    if _QUOTE_RE.match(line):
        return True
    bullet = _BULLET_RE.match(line)
    if bullet and bullet.group(3).strip():
        return True
    ordered = _ORDERED_RE.match(line)
    if ordered and ordered.group(2) == "1" and ordered.group(4).strip():
        return True
    return _table_header(lines, index) is not None


def _closes_fence(line: str, fence: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= len(fence) and set(stripped) == {fence[0]}


def _render_table(lines: list[str], index: int, header_cells: list[str]) -> tuple[str, int]:
    width = len(header_cells)
    index += 2
    rows: list[list[str]] = []
    while index < len(lines) and lines[index].strip() and "|" in lines[index]:
        if _FENCE_RE.match(lines[index]) or _ATX_RE.match(lines[index]):
            break
        rows.append(_split_cells(lines[index]))
        index += 1
    out = ["<table><thead><tr>"]
    out.extend(f"<th>{_render_inline(cell)}</th>" for cell in header_cells)
    out.append("</tr></thead>")
    if rows:
        out.append("<tbody>")
        for row in rows:
            cells = (row + [""] * width)[:width]
            out.append("<tr>")
            out.extend(f"<td>{_render_inline(cell)}</td>" for cell in cells)
            out.append("</tr>")
        out.append("</tbody>")
    out.append("</table>")
    return "".join(out), index


def _render_quote(lines: list[str], index: int, depth: int) -> tuple[str, int]:
    inner: list[str] = []
    while index < len(lines):
        match = _QUOTE_RE.match(lines[index])
        if match is not None:
            inner.append(match.group(1))
            index += 1
            continue
        if not lines[index].strip() or _starts_block(lines, index):
            break
        inner.append(lines[index].strip())  # lazy continuation
        index += 1
    return f"<blockquote>{_render_blocks(inner, depth + 1)}</blockquote>", index


def _render_item(item_lines: list[str], depth: int) -> str:
    """Render one list item tight: leading prose inline, the rest as blocks."""
    lead: list[str] = []
    cursor = 0
    if item_lines and item_lines[0].strip():
        lead.append(item_lines[0].strip())
        cursor = 1
        while (
            cursor < len(item_lines)
            and item_lines[cursor].strip()
            and not _starts_block(item_lines, cursor)
        ):
            lead.append(item_lines[cursor].strip())
            cursor += 1
    head = "<br />".join(_render_inline(line) for line in lead)
    rest = _render_blocks(item_lines[cursor:], depth + 1) if cursor < len(item_lines) else ""
    return head + rest


def _render_list(lines: list[str], index: int, depth: int) -> tuple[str, int]:
    ordered = _ORDERED_RE.match(lines[index]) is not None
    marker_re = _ORDERED_RE if ordered else _BULLET_RE
    other_re = _BULLET_RE if ordered else _ORDERED_RE
    opener = marker_re.match(lines[index])
    assert opener is not None
    base = _indent_width(opener.group(1))
    start = int(opener.group(2)) if ordered else 1
    items: list[list[str]] = []
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            ahead = index
            while ahead < len(lines) and not lines[ahead].strip():
                ahead += 1
            if ahead < len(lines) and items and _leading_indent(lines[ahead]) > base:
                items[-1].extend([""] * (ahead - index))
                index = ahead
                continue
            break
        match = marker_re.match(line)
        if match is not None and _indent_width(match.group(1)) <= base:
            items.append([match.group(4) if ordered else match.group(3)])
            index += 1
            continue
        if not items:
            break
        other = other_re.match(line)
        if other is not None and _indent_width(other.group(1)) <= base:
            break  # the other list flavour at this level is a separate list
        if _leading_indent(line) > base:
            items[-1].append(_strip_indent(line, base + 2))
            index += 1
            continue
        if _starts_block(lines, index):
            break
        items[-1].append(line.strip())  # lazy continuation
        index += 1
    if ordered:
        open_tag = "<ol>" if start == 1 else f'<ol start="{start}">'
        close_tag = "</ol>"
    else:
        open_tag, close_tag = "<ul>", "</ul>"
    parts = [open_tag]
    parts.extend(f"<li>{_render_item(item, depth)}</li>" for item in items)
    parts.append(close_tag)
    return "".join(parts), index


def _render_blocks(lines: list[str], depth: int = 0) -> str:
    if depth >= _MAX_NEST:
        joined = " ".join(line.strip() for line in lines if line.strip())
        return f"<p>{_esc(joined)}</p>" if joined else ""
    parts: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        fence = _FENCE_RE.match(line)
        if fence is not None:
            marker = fence.group(1)
            index += 1
            body: list[str] = []
            while index < len(lines) and not _closes_fence(lines[index], marker):
                body.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            parts.append("<pre><code>" + _esc("\n".join(body)) + "</code></pre>")
            continue
        heading = _ATX_RE.match(line)
        if heading is not None:
            level = len(heading.group(1))
            text = _render_inline((heading.group(2) or "").strip())
            parts.append(f"<h{level}>{text}</h{level}>")
            index += 1
            continue
        if _HR_RE.match(line):
            parts.append("<hr />")
            index += 1
            continue
        if _QUOTE_RE.match(line):
            rendered, index = _render_quote(lines, index, depth)
            parts.append(rendered)
            continue
        header_cells = _table_header(lines, index)
        if header_cells is not None:
            rendered, index = _render_table(lines, index, header_cells)
            parts.append(rendered)
            continue
        if _BULLET_RE.match(line) or _ORDERED_RE.match(line):
            rendered, index = _render_list(lines, index, depth)
            parts.append(rendered)
            continue
        run = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip() and not _starts_block(lines, index):
            run.append(lines[index].strip())
            index += 1
        parts.append("<p>" + "<br />\n".join(_render_inline(item) for item in run) + "</p>")
    return "\n".join(parts)


def markdown_to_safe_html(markdown: str, *, max_chars: int = 500_000) -> str:
    """Render a GFM subset to escape-first HTML for reader snapshots.

    Supported: ATX headings, paragraphs (soft line breaks preserved as
    ``<br />``), unordered and ordered lists with nesting, GFM pipe tables,
    fenced code, blockquotes, thematic breaks, and inline code, links,
    autolinked http(s) URLs, images, emphasis, strong, strikethrough and
    backslash escapes. Everything else — setext headings, reference links,
    footnotes, raw HTML passthrough, task-list checkboxes, table alignment —
    is deliberately left as literal escaped text.

    The result is not trusted HTML. It is a safe *input* to
    ``substrate.books.html_sanitizer.sanitize_book_html``, which remains the
    write-time trust floor and which every call site already applies.
    """
    text = markdown[:max_chars].replace("\r\n", "\n").replace("\r", "\n")
    rendered = _render_blocks(text.split("\n"))
    return rendered if rendered else "<p></p>"


def build_reader_snapshot(
    *,
    source_url: str,
    document_id: str,
    ip_holder_id: str | None,
    main_html: str,
    ingested_at: str,
    title: str | None = None,
    author: str | None = None,
    source_kind: str = "url",
) -> str:
    body = sanitize_html_fragment(main_html)
    ih = ip_holder_id or "null"
    title_line = ""
    if title:
        title_line = f"<p><strong>Title</strong> {html.escape(title)}</p>"
    author_line = ""
    if author:
        author_line = f"<p><strong>Author</strong> {html.escape(author)}</p>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Reader snapshot</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px}}
.meta{{color:#57534e;font-size:14px;border-bottom:1px solid #e7e5e4;padding-bottom:12px}}</style>
</head><body>
<div class="meta"><p><strong>Source</strong> {html.escape(source_url)} · <strong>kind</strong> {html.escape(source_kind)}</p>
{title_line}{author_line}
<p><strong>document_id</strong> {html.escape(document_id)} · <strong>ip_holder_id</strong> {html.escape(ih)}
 · <strong>ingested_at</strong> {html.escape(ingested_at)}</p></div>
<article>{body}</article>
</body></html>"""


def write_reader_snapshot(path: Path, html_doc: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return len(html_doc.encode("utf-8"))


def reader_snapshots_dir() -> Path:
    """Operator store for sanitized ingest HTML (not git; parallel to chunks)."""
    import os

    raw = os.environ.get("ANTIEK_READER_SNAPSHOTS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".antiek" / "reader-snapshots"


def reader_snapshot_path_for(document_id: str) -> Path:
    safe = document_id.replace("/", "_")
    return reader_snapshots_dir() / f"{safe}.html"
