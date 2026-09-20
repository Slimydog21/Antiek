"""Fenced-code partial — ``<pre><code>``.

Code is the one place where whitespace IS content, so the source text is
emitted verbatim inside a ``<pre>`` (escaped, never highlighted): syntax
highlighting in a script-free artifact would mean shipping a tokenizer's
guess as markup, and getting the language wrong reads worse than plain
text. ``attrs.language`` rides along as a data attribute so a future live
surface can highlight it without re-parsing the block.

The source comes from ``attrs.code`` when present, else from the node's
text content — the same two shapes the latex partial accepts.
"""

from __future__ import annotations

from typing import Any

from ..escape import escape_attr, escape_text
from ._common import attr, inline_text


def _code_html(node: dict[str, Any]) -> str:
    """The escaped code text. Returns HTML-safe bytes by every path."""
    source = attr(node, "code")
    if source:
        return escape_text(source)
    content = node.get("content")
    if isinstance(content, list) and content and all(
        isinstance(c, dict) and c.get("type") == "text" for c in content
    ):
        return escape_text("".join(str(c.get("text", "") or "") for c in content))
    # Marked-up content (a code block someone wrote with inline marks):
    # inline_text escapes as it flattens, so it is already safe.
    return inline_text(content)


def render(node: dict[str, Any], ctx: Any) -> str:
    language = attr(node, "language")
    lang_attr = f' data-antiek-language="{escape_attr(language)}"' if language else ""
    return f'<pre class="antiek-code"{lang_attr}><code>{_code_html(node)}</code></pre>'


__all__ = ["render"]
