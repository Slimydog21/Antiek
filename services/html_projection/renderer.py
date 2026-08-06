"""HTML projection renderer core (HPRJ SPR-02 / M2).

``render(doc_model, ctx) -> str`` turns a canonical doc-model into a
self-contained, script-free HTML document with an inert data island.

The doc-model is the TipTap document the ``.antiek`` container stores as
``content.tiptap.json`` (see ``services/antiek_format/SPEC.md`` §2.2),
optionally accompanied by manifest provenance fields the caller folds in
for the footer. The renderer reads:

  - ``doc_model["content"]`` — the TipTap node array (REQUIRED). Each
    top-level node is a block.
  - ``doc_model["title"]`` — optional document title (renders as ``<h1>``).
  - ``doc_model["edges"]`` — optional user-asserted edges list (renders
    as an "Asserted edges" appendix, mirroring the markdown projector).

The rest of the manifest provenance (document_id, creator, etc.) arrives
via ``ctx.provenance`` — keeping the doc-model focused on the document
body and the context focused on render-time inputs (resolver, footer
data) matches the container's own split (content.tiptap.json vs
manifest.json).

INVARIANTS (master-spec, enforced here + by the gate):
  - SCRIPT-FREE: no ``<script>``, no ``on*=``, no ``javascript:``, no
    external ``img src``. The gate (M4) verifies; this module never emits
    any of them.
  - DETERMINISTIC: no wall-clock, no randomness, no dict/set-iteration
    whose order varies. Block dispatch is by dict lookup (O(1), order-
    independent); edges are rendered in list order (the list IS the
    order); JSON canonicalisation sorts keys. M5 proves byte-identical
    output in-process and across processes.
  - SELF-CONTAINED: CSS inlined (``tokens.TOKENS_CSS``); no external
    src/href assets (citation links may carry an href, but they are
    references, not assets, and the gate allows non-javascript hrefs).
  - PROVENANCE FOOTER: every render ends with a provenance footer built
    from ``ctx.provenance``. Never absent.
  - ISLAND: the canonical doc-model is embedded via ``island.embed_island``
    so ``extract_island(render(d)) == d``.

Unknown-block fallback: a node whose ``type`` is not in the contract
renders a visible ``unsupported block (<type>)`` placeholder (never a
silent drop, never a crash).
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .styles import ProjectionStyle

from . import tokens
from .context import RenderContext
from .contract import contract_for_tiptap_type
from .escape import escape_attr, escape_text
from .graph_projection import graph_widget_node
from .island import embed_island, extract_island
from .partials import unsupported as unsupported_partial
from .partials.prose import render as render_prose

# ── Partial dispatch table ──
#
# Maps a contract's ``partial`` name to its render function. Built once at
# import. The prose block has no dedicated partial (rendered inline by
# ``render_prose``); ref-bearing + container blocks each have one. A
# ``None`` partial in the contract means prose (handled separately).
#
# Importing partials lazily-by-name would be a nondeterminism risk if
# import order mattered; instead we import them eagerly here so the
# dispatch table is fixed at module import. ``importlib.import_module``
# is only used at table-build time (deterministic: same modules every
# time).

_PARTIAL_MODULES: dict[str, Any] = {
    "highlight_card": importlib.import_module(
        ".partials.highlight_card", package=__package__
    ),
    "voice_block": importlib.import_module(
        ".partials.voice_block", package=__package__
    ),
    "ai_qa": importlib.import_module(".partials.ai_qa", package=__package__),
    "cite_link": importlib.import_module(
        ".partials.cite_link", package=__package__
    ),
    "cross_doc_jump": importlib.import_module(
        ".partials.cross_doc_jump", package=__package__
    ),
    "region_embed": importlib.import_module(
        ".partials.region_embed", package=__package__
    ),
    "claim_card": importlib.import_module(
        ".partials.claim_card", package=__package__
    ),
    "note": importlib.import_module(".partials.note", package=__package__),
    "question_card": importlib.import_module(
        ".partials.question_card", package=__package__
    ),
    "cross_doc_link": importlib.import_module(
        ".partials.cross_doc_link", package=__package__
    ),
    "chat_exchange": importlib.import_module(
        ".partials.chat_exchange", package=__package__
    ),
    "master_md_section": importlib.import_module(
        ".partials.master_md_section", package=__package__
    ),
    "image": importlib.import_module(".partials.image", package=__package__),
    "latex": importlib.import_module(".partials.latex", package=__package__),
    "widget": importlib.import_module(".partials.widget", package=__package__),
}


def _render_block(node: Any, ctx: RenderContext) -> str:
    """Render one top-level TipTap node to an HTML fragment.

    Dispatch is by the node's ``type`` string via the contract table. A
    miss → unsupported-block placeholder. A non-dict node → also
    unsupported (defensive; the doc-model is trusted but we never crash).
    """
    if not isinstance(node, dict):
        return unsupported_partial.render("<non-dict-node>")
    node_type = str(node.get("type", "") or "")
    if not node_type:
        return unsupported_partial.render("<empty-type>")
    contract = contract_for_tiptap_type(node_type)
    if contract is None:
        return unsupported_partial.render(node_type)
    if contract.partial is None:
        # prose / paragraph / doc — the inline fallback.
        return render_prose(node, ctx)
    module = _PARTIAL_MODULES.get(contract.partial)
    if module is None:  # pragma: no cover — contract/partial mismatch is a bug
        return unsupported_partial.render(node_type)
    # Partial modules are dynamically imported (ModuleType) — their render()
    # contract is str; cast keeps behavior identical under --strict.
    return cast(str, module.render(node, ctx))


def _render_edges(edges: list[dict[str, Any]]) -> str:
    """Render the user-asserted edges appendix. Mirrors
    ``markdown_projector.py:119`` (the "Asserted edges" section). Edges
    render in list order — the list IS the deterministic order."""
    if not edges:
        return ""
    out = ['<section class="antiek-edges">']
    out.append("<h2>Asserted edges</h2>")
    # The knowledge-graph visualization (a dep_graph widget) precedes the
    # textual list: the artifact SHOWS its graph, then enumerates it. Skipped
    # when no edge carries a to_document_id (graph_widget_node returns None).
    graph_node = graph_widget_node(edges)
    if graph_node is not None:
        out.append(tokens.render_widget("dep_graph", graph_node["attrs"]["data"]))
    out.append("<ul>")
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        kind = escape_text(str(edge.get("kind", "references") or ""))
        to_doc = escape_text(str(edge.get("to_document_id", "?") or ""))
        to_hash = str(edge.get("to_content_hash", "") or "")
        hash_preview = escape_text(to_hash[:12] + ("…" if len(to_hash) > 12 else ""))
        note = edge.get("operator_note")
        line = f"<li><strong>{kind}</strong> &rarr; <code>{to_doc}</code>"
        if hash_preview:
            line += f" (content-hash: <code>{hash_preview}</code>)"
        if note:
            line += f" &mdash; {escape_text(str(note))}"
        line += "</li>"
        out.append(line)
    out.append("</ul>")
    out.append("</section>")
    return "".join(out)


def _render_footer(ctx: RenderContext) -> str:
    """Render the provenance footer. Always present. Renders whatever
    provenance fields are set; omits absent ones deterministically."""
    p = ctx.provenance
    out = ['<footer class="antiek-footer">']
    out.append("Projected from a .antiek document. HTML is derived; ")
    out.append("do not import this HTML back into Antiek.")
    parts: list[str] = []
    if p.document_id:
        parts.append(f"document: {escape_text(p.document_id)}")
    if p.notebook_id:
        parts.append(f"notebook: {escape_text(p.notebook_id)}")
    if p.content_class:
        parts.append(f"class: {escape_text(p.content_class)}")
    if p.schema_version:
        parts.append(f"schema: {escape_text(p.schema_version)}")
    if p.creator_user_id:
        parts.append(f"creator: {escape_text(p.creator_user_id)}")
    if p.rendered_at:
        parts.append(f"rendered: {escape_text(p.rendered_at)}")
    if p.signature_valid is not None:
        parts.append(
            "signature: verified" if p.signature_valid else "signature: unverified"
        )
    if parts:
        out.append("<br>" + " &middot; ".join(parts))
    out.append("</footer>")
    return "".join(out)


def render(
    doc_model: dict[str, Any],
    ctx: RenderContext,
    *,
    style: ProjectionStyle | str | None = None,
) -> str:
    """Render a canonical doc-model to self-contained, script-free HTML.

    Parameters
    ----------
    doc_model:
        The canonical doc-model. ``doc_model["content"]`` is the TipTap
        node array (REQUIRED). ``doc_model["title"]`` and
        ``doc_model["edges"]`` are optional. The full doc_model is
        embedded verbatim in the data island for round-trip.
    ctx:
        Render context (resolver + provenance + schema version).
    style:
        The projection style (the "wheel of styles" choice): ``None`` = the
        Antiek default, a slug looked up in the default registry, or a
        :class:`~services.html_projection.styles.ProjectionStyle`. Style is PURE
        presentation — it swaps only the inlined stylesheet; the block HTML, the
        provenance footer, and the data island are byte-identical across styles,
        so the round-trip ``extract_island(render(d, style=X)) == d`` holds for
        every style. This is what makes "regenerate in a different style" a
        no-model-call operation (see :func:`render_in_style`).

    Returns
    -------
    str
        A complete ``<!DOCTYPE html>`` document. Self-contained (inlined
        CSS), script-free (gate-verified), with an inert data island and
        a provenance footer.
    """
    from .styles import resolve_style

    resolved_style = resolve_style(style)
    if not isinstance(doc_model, dict):
        raise TypeError(
            f"render: doc_model must be a dict, got {type(doc_model).__name__}"
        )
    content = doc_model.get("content")
    if not isinstance(content, list):
        # An empty/missing content array is legal (empty doc). Treat
        # non-list as empty rather than crash.
        content = []
    title = doc_model.get("title")
    edges = doc_model.get("edges")
    if not isinstance(edges, list):
        edges = []

    # ── Body: blocks + edges appendix + island + footer ──
    body_parts: list[str] = []
    if isinstance(title, str) and title:
        body_parts.append(f'<h1 class="antiek-doc-title">{escape_text(title)}</h1>')
    for node in content:
        body_parts.append(_render_block(node, ctx))
    body_parts.append(_render_edges(edges))
    # Data island: embed the FULL doc_model (not just content) so the
    # round-trip recovers title + edges too.
    body_parts.append(embed_island(doc_model, schema_version=ctx.schema_version))
    body_parts.append(_render_footer(ctx))
    body = "\n".join(body_parts)

    # ── Document shell ──
    # Inlined CSS, no external assets, no script. lang="en" is fixed
    # (deterministic; a per-doc lang would be a ctx field if needed).
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape_attr(str(title) if isinstance(title, str) else 'Antiek document')}</title>\n"
        f"<style>\n{resolved_style.stylesheet()}</style>\n"
        "</head>\n"
        '<body>\n'
        '<main class="antiek-doc">\n'
        f"{body}\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def restyle_artifact(
    artifact_html: str,
    ctx: RenderContext,
    *,
    style: ProjectionStyle | str | None,
) -> str:
    """Re-render an existing Antiek HTML artifact under a different style.

    This is the "regenerate in this style" wheel action: recover the canonical
    doc-model from the artifact's inert data island (:func:`extract_island`) and
    re-project it with the chosen ``style``. It is a PURE presentation transform —
    NO model call, deterministic — because the doc-model, not the rendered HTML, is
    the source of truth (the html-projection invariant: HTML is a projection, never
    imported back as source). ``ctx`` supplies the render-time inputs (resolver +
    provenance) that live outside the doc-model; a caller regenerating an artifact
    reuses the artifact's original context.
    """
    doc_model = extract_island(artifact_html)
    return render(doc_model, ctx, style=style)


__all__ = ["render", "restyle_artifact"]
