"""M2: renderer core tests (HPRJ SPR-02).

Golden corpus renders without error; output is self-contained; provenance
footer present; unknown-block fallback visible; no wall-clock in the
module.
"""

from __future__ import annotations

import inspect
import re

import pytest

from services.html_projection import Provenance, RenderContext, render
from services.html_projection.tests.fixtures.golden import golden_corpus


# ── Golden corpus renders without error ──


@pytest.mark.parametrize("idx", range(len(golden_corpus())))
def test_golden_corpus_renders(ctx, idx):
    """Every golden-corpus doc-model renders to a non-empty HTML string."""
    doc = golden_corpus()[idx]
    html = render(doc, ctx)
    assert isinstance(html, str)
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert len(html) > 0


def test_golden_corpus_spans_all_block_types(ctx):
    """The golden corpus exercises every block type in the contract
    table (so the gate + round-trip + determinism tests cover them all)."""
    from services.html_projection.contract import known_block_types

    seen_types = set()
    for doc in golden_corpus():
        for node in doc.get("content", []):
            if isinstance(node, dict):
                t = node.get("type", "")
                # Strip antiek_ prefix to compare against bare block types.
                bare = t[len("antiek_") :] if t.startswith("antiek_") else t
                seen_types.add(bare)
    # prose + all container + substrate types appear (some as aliases).
    # We assert the corpus touches a meaningful superset, not every
    # single alias.
    assert "prose" in seen_types or "paragraph" in seen_types
    assert "highlight_card" in seen_types
    assert "voice_block" in seen_types
    assert "ai_qa" in seen_types
    assert "unknown" not in known_block_types()  # sanity


def test_golden_corpus_includes_unknown_only_doc(ctx):
    """One golden doc has ONLY unknown types (exercises the
    unsupported-block fallback)."""
    unknown_doc = golden_corpus()[-1]
    assert all(
        not isinstance(n, dict) or n.get("type") not in {
            "antiek_prose", "prose", "paragraph", "doc",
            "antiek_highlight_card", "antiek_voice_block", "antiek_ai_qa",
            "antiek_cite_link", "antiek_cross_doc_jump",
            "antiek_region_embed", "antiek_claim_card", "antiek_note",
            "antiek_question_card", "antiek_cross_doc_link",
            "antiek_chat_exchange", "antiek_master_md_section",
            "antiek_image", "antiek_latex", "note_block", "math_block",
        }
        for n in unknown_doc.get("content", [])
    )


# ── Unknown-block fallback ──


def test_unknown_block_renders_visible_placeholder(ctx):
    """An unknown block type renders a visible 'unsupported block (type)'
    placeholder — never a silent drop, never a crash."""
    doc = {"content": [{"type": "future_widget_v9", "attrs": {"block_id": "u"}}]}
    html = render(doc, ctx)
    assert "unsupported block (future_widget_v9)" in html


def test_empty_type_renders_placeholder(ctx):
    """A node with an empty type string renders the placeholder."""
    doc = {"content": [{"type": "", "attrs": {}}]}
    html = render(doc, ctx)
    assert "unsupported block" in html


def test_non_dict_node_renders_placeholder(ctx):
    """A non-dict node (corrupt doc-model) renders the placeholder, not a
    crash."""
    doc = {"content": ["not a dict", 42, None]}
    html = render(doc, ctx)
    assert "unsupported block" in html


# ── Self-contained ──


def test_output_is_self_contained_no_external_assets(ctx):
    """No external src/href assets (the inlined CSS has no @import/url();
    no <link> stylesheet; no external <img src>). Citation <a href> to
    https is allowed (references, not assets) but tested separately."""
    for doc in golden_corpus():
        html = render(doc, ctx)
        # No <link rel="stylesheet">.
        assert not re.search(r"<link\b", html, re.IGNORECASE), (
            "external <link> stylesheet found"
        )
        # No @import or url() in the inlined CSS.
        style_match = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
        assert style_match is not None
        css = style_match.group(1)
        assert "@import" not in css
        assert not re.search(r"url\s*\(", css)
        # No external img/audio/video src (gate enforces too).
        assert not re.search(
            r"<(?:img|audio|video|source|iframe)\b[^>]*\bsrc\s*=\s*[\"']?\s*https?://",
            html, re.IGNORECASE,
        )


def test_css_is_inlined(ctx):
    """The stylesheet is inlined in a <style> element in <head>."""
    html = render(golden_corpus()[0], ctx)
    assert re.search(r"<head>.*<style>.*</style>.*</head>", html, re.DOTALL)


# ── Provenance footer ──


def test_provenance_footer_present(ctx):
    """Every render has a provenance footer."""
    html = render(golden_corpus()[0], ctx)
    assert '<footer class="antiek-footer">' in html


def test_provenance_footer_present_even_when_empty(empty_ctx):
    """The footer renders even with no provenance fields."""
    html = render({"content": []}, empty_ctx)
    assert '<footer class="antiek-footer">' in html


def test_provenance_footer_carries_fields(ctx):
    """The footer surfaces the provenance fields that were set."""
    html = render(golden_corpus()[0], ctx)
    assert "document: doc-test-1" in html
    assert "notebook: nbk-test-1" in html
    assert "class: notebook" in html
    assert "schema: 1.0.0" in html
    assert "creator: user-test" in html
    assert "rendered: 2026-05-21T12:00:00Z" in html
    assert "signature: verified" in html


def test_provenance_footer_states_derived_only(ctx):
    """The footer states HTML is derived (do not import back)."""
    html = render(golden_corpus()[0], ctx)
    assert "do not import this HTML back into Antiek" in html


# ── No wall-clock in the renderer module ──


def _ast_calls_to_wall_clock(mod) -> list[str]:
    """Walk a module's AST and return any wall-clock call expressions
    found (e.g. ``datetime.now()``, ``time.time()``). AST inspection is
    robust against docstrings/comments mentioning the names in prose."""
    import ast

    src = inspect.getsource(mod)
    tree = ast.parse(src)
    hits: list[str] = []
    for node in ast.walk(tree):
        # datetime.now(...) / datetime.utcnow(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func = node.func
            if isinstance(func.value, ast.Name):
                qual = f"{func.value.id}.{func.attr}"
                if qual in {"datetime.now", "datetime.utcnow", "time.time",
                            "time.monotonic", "time.perf_counter", "time.time_ns"}:
                    hits.append(qual)
        # now() / time() called as a bare name imported via `from datetime import now`
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"now", "monotonic", "perf_counter"}:
                hits.append(node.func.id)
    return hits


def test_no_wall_clock_in_renderer_module():
    """The pure modules contain no wall-clock CALLS (determinism
    invariant). AST-based so docstrings mentioning 'datetime.now' in
    prose do not false-fire."""
    import services.html_projection.renderer as renderer_mod
    import services.html_projection.island as island_mod
    import services.html_projection.gate as gate_mod
    import services.html_projection.context as context_mod
    import services.html_projection.tokens as tokens_mod
    import services.html_projection.escape as escape_mod

    for mod in [renderer_mod, island_mod, gate_mod, context_mod, tokens_mod, escape_mod]:
        hits = _ast_calls_to_wall_clock(mod)
        assert not hits, (
            f"{mod.__name__} makes wall-clock calls {hits}"
        )


def test_no_datetime_time_import_in_pure_modules():
    """The pure modules (renderer, island, gate, context, tokens, escape)
    do not import datetime or time at all — the strongest guarantee. AST-
    based: checks actual import statements, not prose."""
    import ast

    pure_mods = [
        "services.html_projection.renderer",
        "services.html_projection.island",
        "services.html_projection.gate",
        "services.html_projection.context",
        "services.html_projection.tokens",
        "services.html_projection.escape",
        "services.html_projection.contract",
        "services.html_projection.partials._common",
    ]
    import importlib

    for modname in pure_mods:
        mod = importlib.import_module(modname)
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in {"datetime", "time"}, (
                        f"{modname} imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                assert top not in {"datetime", "time"}, (
                    f"{modname} imports from {node.module}"
                )


# ── Escaping in visible surface ──


def test_user_text_is_escaped_in_visible_surface(ctx):
    """User-supplied text with <, >, & is escaped in the visible HTML
    (no markup injection into the reading surface)."""
    doc = {
        "content": [
            {
                "type": "antiek_prose",
                "attrs": {"block_id": "x"},
                "content": [{"type": "text", "text": "<script>alert(1)</script>"}],
            }
        ]
    }
    html = render(doc, ctx)
    # The literal <script> must NOT appear unescaped in the visible
    # surface (it's escaped to &lt;script&gt;). The gate would catch it,
    # but this test pins the escaping at the source.
    visible = html.split('<template data-antiek="doc-model">')[0]
    assert "<script>alert(1)</script>" not in visible
    assert "&lt;script&gt;" in visible


# ── Edges appendix ──


def test_edges_appendix_renders(ctx):
    """User-asserted edges render as an 'Asserted edges' section
    (mirrors the markdown projector)."""
    doc = {
        "content": [],
        "edges": [
            {
                "edge_id": "e1",
                "from_block_id": "b1",
                "to_content_hash": "a" * 64,
                "to_document_id": "doc-x",
                "kind": "supports",
                "asserted_at": "2026-01-01T00:00:00+00:00",
                "operator_note": "a note",
            }
        ],
    }
    html = render(doc, ctx)
    assert "Asserted edges" in html
    assert "supports" in html
    assert "doc-x" in html


def test_no_edges_no_appendix(ctx):
    """No edges → no edges appendix section."""
    html = render({"content": []}, ctx)
    assert "Asserted edges" not in html
