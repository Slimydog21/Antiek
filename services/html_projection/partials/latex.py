"""LaTeX block partial (HPRJ SPR-02 / M2).

Renders ``antiek_latex`` / ``math_block`` — a LaTeX equation. TipTap shape
(``substrate/notebooks/tiptap_codec.py:55``: ``math_block`` → ``latex``).

SCRIPT-FREE INVARIANT: MathJax/KaTeX render LaTeX via JavaScript. That is
rejected by the script-free invariant — a render-time JS dependency in the
artifact is an RCE vector for the §7 daemon and breaks offline
self-containment. We render the LaTeX source as monospaced text inside a
``<pre>``-styled block. A reader sees the equation source; the live app
renders it with KaTeX. This is the honest, lossy projection: the LaTeX
source is preserved exactly (round-trips through the data island), only
the visual rendering is deferred to the live app.

Mirrors the markdown projector's passthrough philosophy for blocks it
can't richly render (``markdown_projector.py:214`` prose passthrough).
"""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..escape import escape_text
from ._common import attr, inline_text


def render(node: dict[str, Any], ctx: RenderContext) -> str:
    # The LaTeX source may be in attrs.latex / attrs.expression or in the
    # node's text content.
    source = attr(node, "latex") or attr(node, "expression")
    if not source:
        source = inline_text(node.get("content"))
    out = ['<div class="antiek-block antiek-latex">']
    out.append(escape_text(source))
    out.append("</div>")
    return "".join(out)
