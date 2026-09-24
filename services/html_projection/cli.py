"""Render a Markdown file through the projection engine, from the shell.

    python -m services.html_projection.cli docs/design-system.md > docs/design-system.html
    python -m services.html_projection.cli notes.md --style book --title "Field notes"

The HTML thesis says every information artifact is HTML wearing a style from
the wheel. This is the smallest honest way to hold the repo's own documents
to it: a Markdown file becomes a self-contained, script-free HTML document by
EXACTLY the path an ingested document takes — escape-first Markdown
(``acquisition.snapshot.reader_html.markdown_to_safe_html``), the allowlist
sanitizer (``substrate.books.html_sanitizer.sanitize_book_html``), the
document adapter into a doc-model, and ``render`` under a wheel style — so
the page is evidence about the pipeline, not a bespoke exporter with its own
bugs.

Determinism is what makes a committed render checkable. Nothing here reads
the clock or the environment: the provenance footer carries the path as the
document id and no timestamp, so ``cmp committed.html <(cli source.md)``
holds until the source or the engine changes, and a stale commit shows up as
a byte difference rather than as a plausible-looking page.

The first ``# Heading`` line, when the file opens with one, becomes the
artifact title (``--title`` overrides it) and is lifted out of the body so
the page does not carry the same H1 twice.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import PurePosixPath

from acquisition.snapshot.reader_html import markdown_to_safe_html
from substrate.books.html_sanitizer import sanitize_book_html

from .adapters.document import adapt_document_for_projection
from .context import Provenance, RenderContext
from .gate import ScriptViolation, assert_script_free
from .renderer import render
from .styles import DEFAULT_STYLE_NAME, StyleError, default_registry

_LEADING_H1 = re.compile(r"\A\s*#[ \t]+(?P<title>[^\n]+?)[ \t#]*\n")

SOURCE_KIND = "upload_md"


def split_title(markdown: str) -> tuple[str | None, str]:
    """Lift a leading ATX H1 out of the body and return ``(title, rest)``."""
    match = _LEADING_H1.match(markdown)
    if match is None:
        return None, markdown
    return match.group("title").strip(), markdown[match.end():]


def render_markdown(
    markdown: str,
    *,
    document_id: str,
    style: str = DEFAULT_STYLE_NAME,
    title: str | None = None,
) -> str:
    """Project ``markdown`` to a complete HTML document under ``style``.

    Raises :class:`StyleError` for a slug not on the default wheel and
    :class:`ScriptViolation` if the render fails the zero-script gate — the
    latter cannot happen through this path, which is why it is asserted
    rather than caught.
    """
    heading, body_md = split_title(markdown)
    resolved_title = title if title is not None else heading
    resolved = default_registry().get(style)
    body_html = sanitize_book_html(markdown_to_safe_html(body_md))
    doc_model = adapt_document_for_projection(
        document_id, body_html, SOURCE_KIND, None, title=resolved_title
    )
    ctx = RenderContext(provenance=Provenance(document_id=document_id, title=resolved_title))
    html = render(doc_model, ctx, style=resolved)
    assert_script_free(html)
    return html


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m services.html_projection.cli",
        description=(
            "Render a Markdown file to a self-contained, script-free, deterministic "
            "HTML document through the projection engine (stdout)."
        ),
    )
    parser.add_argument("path", help="Markdown file to render ('-' reads stdin)")
    parser.add_argument(
        "--style",
        default=DEFAULT_STYLE_NAME,
        help="wheel style slug (default: %(default)s)",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="artifact title (default: the file's leading '# Heading', else none)",
    )
    parser.add_argument(
        "--document-id",
        default=None,
        help="provenance document id (default: the path as given, POSIX-normalised)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.path == "-":
        markdown = sys.stdin.read()
        document_id = args.document_id or "stdin"
    else:
        try:
            with open(args.path, encoding="utf-8") as fh:
                markdown = fh.read()
        except OSError as err:
            print(f"error: cannot read {args.path}: {err.strerror}", file=sys.stderr)
            return 2
        document_id = args.document_id or PurePosixPath(args.path.replace("\\", "/")).as_posix()

    try:
        html = render_markdown(
            markdown, document_id=document_id, style=args.style, title=args.title
        )
    except StyleError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    except ScriptViolation as err:  # pragma: no cover - the engine never emits script
        print(f"error: render failed the zero-script gate: {err}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(html.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
