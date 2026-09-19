"""The ingest bridge: a sanitized document body projected through the engine.

These tests exercise the ROUND TRIP, not the pieces in isolation, because
the pieces were never the problem. ``markdown_to_safe_html`` renders a
table, ``sanitize_book_html`` keeps it, and the projection renderer could
draw one — but nothing joined them, so a table in an ingested PDF reached
the reader as a flat blob. Every structural assertion below therefore runs
through the real chain: markdown → ingest renderer → sanitizer → adapter →
renderer.

The load-bearing test is ``test_unmapped_construct_renders_visibly``: an
unmapped construct must be VISIBLE as unmapped and must survive in the data
island. A reader who cannot tell "the source had nothing here" from "we
lost it" cannot trust any part of the surface.
"""

from __future__ import annotations

from acquisition.snapshot.reader_html import markdown_to_safe_html
from services.html_projection import (
    RenderContext,
    default_registry,
    extract_island,
    render,
)
from services.html_projection.adapters.document import (
    MAX_TREE_DEPTH,
    adapt_document_for_projection,
)
from services.html_projection.gate import find_violations
from substrate.books.html_sanitizer import sanitize_book_html

_MARKDOWN = """\
# Ingested Paper

A paragraph with **bold**, *italic*, `code` and a [link](https://example.com/a).

## Measurements

| sample | mass (g) | note |
|--------|----------|------|
| A-1    | 11.4     | dry  |
| A-2    | 9.8      | wet  |

1. first step
2. second step
   - a nested detail

> A quoted passage from the source.

```
def f(x):
    return x * 2
```

---

![figure one](https://example.com/fig1.png)
"""


def _ingested(markdown: str = _MARKDOWN) -> str:
    """The bytes an ingested document actually has in the sidecar: through
    the ingest renderer AND the write-time sanitizer, in that order."""
    return sanitize_book_html(markdown_to_safe_html(markdown))


def _adapt(markdown: str = _MARKDOWN, **kwargs) -> dict:
    return adapt_document_for_projection(
        "doc-ingest-1",
        _ingested(markdown),
        "upload",
        "https://example.com/paper.pdf",
        **kwargs,
    )


def _visible(html: str) -> str:
    """The part of the artifact a reader sees: after the inlined stylesheet,
    before the inert data island. Both ends matter — the stylesheet mentions
    every block class by name and the island carries every node, so a naive
    substring search over the whole document would pass while the visible
    surface was empty. Asserting on this and on the island separately is what
    distinguishes "rendered" from "merely round-tripped"."""
    return html.split("</style>", 1)[1].split("<template", 1)[0]


# ── Done-bar 5: the markdown table survives the whole round trip ──


def test_markdown_table_reaches_a_real_table_element():
    """A GFM table in the source is a <table> in the projection — grid
    intact, every cell where it belongs. Flattening it to a paragraph of
    concatenated cells would not be a formatting loss, it would be a data
    loss."""
    html = render(_adapt(), RenderContext())
    body = _visible(html)
    assert "<table class=\"antiek-table\">" in body
    assert "<th>sample</th>" in body
    assert "<th>mass (g)</th>" in body
    assert "<td>A-1</td>" in body
    assert "<td>11.4</td>" in body
    assert "<td>wet</td>" in body
    # The header row is a real <thead>, so the grid is navigable.
    assert "<thead><tr><th>sample</th>" in body


def test_table_survives_the_sanitizer_specifically():
    """Named separately because the sanitizer is the step most likely to be
    assumed rather than checked: it is an allowlist, and a table that were
    not on it would vanish before the adapter ever ran."""
    sanitized = _ingested()
    assert "<table>" in sanitized
    assert "<td>11.4</td>" in sanitized


# ── Done-bar 4: unmapped renders visibly, and is not dropped ──


def test_unmapped_construct_renders_visibly():
    """A definition list is on the sanitizer's allowlist and has no mapping
    here. It must show up as an unsupported block naming the tag, and its
    text must still be in the island — visible honesty on the surface,
    lossless recovery underneath."""
    body_html = _ingested("Intro paragraph.") + (
        "<dl><dt>Antiek</dt><dd>Dutch for antique.</dd></dl>"
    )
    doc = adapt_document_for_projection("doc-dl", body_html, "upload", None)
    html = render(doc, RenderContext())

    assert "unsupported block (source:dl)" in _visible(html)
    # Not dropped: the node and its text round-trip through the island.
    island = extract_island(html)
    unmapped = [n for n in island["content"] if n["type"] == "source:dl"]
    assert len(unmapped) == 1
    assert unmapped[0]["attrs"]["tag"] == "dl"
    assert "Dutch for antique." in unmapped[0]["content"][0]["text"]


def test_unmapped_is_not_confusable_with_absence():
    """The red-proof for the rule: a document WITHOUT the unmapped
    construct produces no placeholder, so the placeholder in the test above
    is evidence of the construct rather than of the renderer's mood."""
    html = render(_adapt("Just a paragraph."), RenderContext())
    assert "antiek-unsupported" not in _visible(html)


def test_inline_image_inside_a_paragraph_is_not_swallowed():
    """An <img> mid-paragraph is the classic silent drop: it is not text, so
    an inline flattener contributes nothing for it and the reader never
    learns a figure was there. It must split the paragraph and render."""
    doc = adapt_document_for_projection(
        "doc-img",
        '<p>Before <img alt="the diagram"> after.</p>',
        "upload",
        None,
    )
    body = _visible(render(doc, RenderContext()))
    assert "the diagram" in body
    assert "Before" in body
    assert "after." in body


# ── Done-bar 3: the island round-trips under every style on the wheel ──


def test_island_round_trips_for_every_style_in_the_wheel():
    doc = _adapt(title="Ingested Paper")
    for style in default_registry().list_styles():
        html = render(doc, RenderContext(), style=style)
        assert extract_island(html) == doc, f"island lost under style {style.name}"


# ── Done-bar 2: switching style is presentation only, no model call ──


def test_switching_style_changes_only_the_stylesheet():
    """The proof that a restyle needs no model: for two different styles the
    rendered body is byte-identical and only the inlined <style> differs."""
    doc = _adapt()
    a = render(doc, RenderContext(), style="antiek")
    b = render(doc, RenderContext(), style="academic-paper")
    assert a != b
    body_a = a.split("</style>", 1)[1]
    body_b = b.split("</style>", 1)[1]
    assert body_a == body_b


def test_render_is_byte_identical_on_repeat():
    doc = _adapt()
    ctx = RenderContext()
    assert render(doc, ctx, style="book") == render(doc, ctx, style="book")


# ── Structure the adapter must preserve ──


def test_heading_levels_are_preserved_verbatim():
    doc = _adapt()
    levels = [n["attrs"]["level"] for n in doc["content"] if n["type"] == "heading"]
    assert levels == [1, 2]
    body = _visible(render(doc, RenderContext()))
    assert '<h1 class="antiek-heading">Ingested Paper</h1>' in body
    assert '<h2 class="antiek-heading">Measurements</h2>' in body


def test_ordered_and_nested_lists_survive():
    body = _visible(render(_adapt(), RenderContext()))
    assert '<ol class="antiek-list">' in body
    assert "first step" in body
    # The nested bullet is a list inside the second item, not a sibling.
    assert body.index("second step") < body.index("a nested detail")
    assert '<ul class="antiek-list">' in body


def test_code_block_keeps_its_whitespace():
    body = _visible(render(_adapt(), RenderContext()))
    assert '<pre class="antiek-code"><code>def f(x):\n    return x * 2</code></pre>' in body


def test_blockquote_and_rule_render_as_themselves():
    body = _visible(render(_adapt(), RenderContext()))
    assert '<blockquote class="antiek-quote">' in body
    assert "A quoted passage from the source." in body
    assert '<hr class="antiek-rule">' in body


def test_inline_marks_and_links_survive():
    body = _visible(render(_adapt(), RenderContext()))
    assert "<strong>bold</strong>" in body
    assert "<em>italic</em>" in body
    assert "<code>code</code>" in body
    assert '<a href="https://example.com/a">link</a>' in body


def test_image_renders_as_alt_text_and_never_as_an_external_fetch():
    """The sanitizer strips every img src before storage and the projection
    must not reintroduce one: an external <img src> is a fetch vector the
    self-contained invariant forbids."""
    body = _visible(render(_adapt(), RenderContext()))
    assert "figure one" in body
    assert "<img" not in body


# ── Invariants the projection already had, held on the new path ──


def test_projection_of_an_ingested_document_is_script_free():
    hostile = (
        "<p>ordinary text</p>"
        '<p><a href="javascript:alert(1)">click</a></p>'
        '<p><img src="https://evil.example/pixel.gif" alt="tracker"></p>'
        "<script>alert(2)</script>"
        "<p onclick=\"steal()\">handler</p>"
    )
    doc = adapt_document_for_projection("doc-hostile", hostile, "url", "https://e/x")
    html = render(doc, RenderContext())
    assert find_violations(html) == []
    body = _visible(html)
    # The link's text survives; only the unsafe scheme is gone.
    assert "click" in body
    assert "javascript:" not in body
    # Script text is never resurrected as prose.
    assert "alert(2)" not in html


def test_adapter_mirrors_the_sanitizer_drop_set_on_unsanitized_input():
    """The adapter's contract is the sanitized sidecar, but it is a public
    function. Handed raw HTML it must still never turn <style> or <script>
    text into readable prose."""
    doc = adapt_document_for_projection(
        "doc-raw",
        "<style>body{color:red}</style><p>kept</p><script>x=1</script>",
        "url",
        None,
    )
    text = str(doc)
    assert "color:red" not in text
    assert "x=1" not in text
    assert "kept" in text


def test_deep_nesting_is_bounded_rather_than_fatal():
    """A pathological document must not take the request handler's stack
    with it. Past the bound the remainder renders as one node, not an
    exception and not silence."""
    deep = "<div>" * (MAX_TREE_DEPTH + 40) + "buried text" + "</div>" * (MAX_TREE_DEPTH + 40)
    doc = adapt_document_for_projection("doc-deep", deep, "upload", None)
    html = render(doc, RenderContext())
    assert "buried text" in html
    assert find_violations(html) == []


def test_empty_body_produces_an_empty_but_valid_doc_model():
    doc = adapt_document_for_projection("doc-empty", "", "upload", None)
    assert doc["content"] == []
    html = render(doc, RenderContext())
    assert extract_island(html) == doc


def test_source_identity_rides_in_the_doc_model():
    """The island names its own origin, so an artifact that leaves Antiek
    still says which document it came from."""
    doc = _adapt()
    assert doc["source"] == {
        "document_id": "doc-ingest-1",
        "source_kind": "upload",
        "source_url": "https://example.com/paper.pdf",
    }


# ── Verifier hardening: the two silent-drop paths nothing else pinned ──


def test_a_block_nested_in_inline_markup_is_hoisted_not_dropped():
    """A block element reached through inline markup must survive.

    ``<a><img></a>`` is not an exotic shape — it is how every web page
    writes a linked figure, and a URL ingest stores the page's own HTML, not
    a markdown round trip. The inline flattener contributes nothing for a
    node that is not text, so without the hoist in ``_inline`` the figure
    leaves no trace on the surface or in the island. The same path carries a
    table wrapped in a ``<span>`` and an image inside a heading, so all
    three are asserted together: each one is a construct the source had and
    the reader would never learn about.
    """
    body = (
        '<p><a href="https://example.com/f"><img alt="the linked figure"></a></p>'
        "<h2>Chapter <img alt=\"the crest\"></h2>"
        "<p><span>lead <table><tr><td>hoisted cell</td></tr></table></span></p>"
    )
    doc = adapt_document_for_projection("doc-hoist", body, "url", None)
    visible = _visible(render(doc, RenderContext()))
    assert "the linked figure" in visible
    assert "the crest" in visible
    assert "<td>hoisted cell</td>" in visible
    # The table is a real grid, not a paragraph that happens to say the words.
    assert '<table class="antiek-table">' in visible
    # And each one is a node in its own right, not text glued into a run.
    types = [node["type"] for node in doc["content"]]
    assert types.count("antiek_image") == 2
    assert "table" in types


def test_unmapped_node_inside_a_list_item_or_table_cell_still_renders_visibly():
    """The visible-unsupported rule has to hold at depth, not only at the top.

    ``partials/_structural.py`` dispatches a nested child through
    ``renderer.render_block`` for exactly this reason: an unmapped construct
    buried in a list item or a table cell must show the same placeholder it
    would show as a sibling of the body. Flatten that seam to inline text
    instead and the placeholder disappears, which is the failure this whole
    module is built to prevent — so it is asserted where the seam is, one
    level down.
    """
    body = (
        "<ul><li><dl><dt>Antiek</dt><dd>Dutch for antique.</dd></dl></li></ul>"
        "<table><tr><td><dl><dt>Wheel</dt></dl></td></tr></table>"
    )
    doc = adapt_document_for_projection("doc-nested-dl", body, "upload", None)
    visible = _visible(render(doc, RenderContext()))
    assert visible.count("unsupported block (source:dl)") == 2
    assert "<li><div class=\"antiek-block antiek-unsupported\">" in visible
    assert "<td><div class=\"antiek-block antiek-unsupported\">" in visible


def test_a_br_inside_pre_is_a_line_break_not_a_deletion():
    """A code block written with ``<br>`` keeps its lines.

    A URL ingest stores the page's own serialized DOM, so ``<pre>`` arrives
    however the site wrote it, and plenty of sites write the breaks as
    ``<br>``. Dropping them joined the last token of one line to the first of
    the next — ``return x * 2print(f(2))`` — which is not a formatting loss
    but a wrong program, and it left no trace on the surface or in the island
    to say so.
    """
    body = sanitize_book_html(
        "<pre><code>def f(x):<br />    return x * 2<br /><br />print(f(2))</code></pre>"
    )
    assert "<br />" in body, "the sanitizer is expected to keep the break"
    doc = adapt_document_for_projection("doc-br-pre", body, "url", None)
    visible = _visible(render(doc, RenderContext()))
    assert (
        '<pre class="antiek-code"><code>def f(x):\n    return x * 2\n\nprint(f(2))</code></pre>'
        in visible
    )
