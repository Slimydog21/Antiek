"""SPR-AHT-04 — ingest reader snapshot."""

from __future__ import annotations

from acquisition.snapshot.reader_html import (
    build_reader_snapshot,
    markdown_to_safe_html,
    sanitize_html_fragment,
)
from substrate.books.html_sanitizer import sanitize_book_html


def _round_trip(markdown: str) -> str:
    """What the reader actually stores: render, then the trust-floor sanitizer.

    The renderer alone proves nothing. Every call site pipes its output through
    ``sanitize_book_html`` before it is persisted or served, so the structure a
    document keeps is whatever survives BOTH passes — that is the contract
    these tests assert.
    """
    return sanitize_book_html(markdown_to_safe_html(markdown))


def test_strips_script_tags():
    raw = "<p>ok</p><script>alert(1)</script>"
    assert "<script>" not in sanitize_html_fragment(raw)


def test_build_snapshot_includes_metadata():
    html = build_reader_snapshot(
        source_url="https://example.com/a",
        document_id="doc-1",
        ip_holder_id=None,
        main_html="<p>Body</p>",
        ingested_at="2026-06-23T00:00:00Z",
    )
    assert "doc-1" in html
    assert "Body" in html
    assert "example.com" in html


def test_markdown_to_safe_html_headings():
    body = markdown_to_safe_html("## Section\n\nPara one.")
    assert "<h2>Section</h2>" in body
    assert "Para one." in body
    assert "<script>" not in body


def test_build_snapshot_book_metadata():
    html = build_reader_snapshot(
        source_url="file:///books/foo.pdf",
        document_id="doc-book-abc",
        ip_holder_id=None,
        main_html="<p>Chapter</p>",
        ingested_at="2026-06-24T00:00:00Z",
        title="Test Book",
        author="Author",
        source_kind="book",
    )
    assert "kind</strong> book" in html
    assert "Test Book" in html
    assert "Author" in html


# --- GFM structure survives the render → sanitize round trip -------------------


def test_table_survives_round_trip():
    body = _round_trip("| Year | Model |\n| --- | ----- |\n| 2024 | Alpha |\n| 2025 | Beta  |\n")
    assert body == (
        "<table><thead><tr><th>Year</th><th>Model</th></tr></thead>"
        "<tbody>"
        "<tr><td>2024</td><td>Alpha</td></tr>"
        "<tr><td>2025</td><td>Beta</td></tr>"
        "</tbody></table>"
    )


def test_table_cells_keep_inline_markup():
    body = _round_trip("| a | b |\n|---|---|\n| **x** | [y](https://e.com) |\n")
    assert "<td><strong>x</strong></td>" in body
    assert '<td><a href="https://e.com">y</a></td>' in body


def test_lists_survive_round_trip():
    body = _round_trip("- alpha\n- beta\n  - nested\n")
    assert body == "<ul><li>alpha</li><li>beta<ul><li>nested</li></ul></li></ul>"


def test_ordered_list_keeps_its_start():
    body = _round_trip("3. third\n4. fourth\n")
    assert body == '<ol start="3"><li>third</li><li>fourth</li></ol>'


def test_links_survive_round_trip():
    body = _round_trip("See [the paper](https://example.com/p) for detail.")
    assert '<a href="https://example.com/p">the paper</a>' in body


def test_autolink_survives_round_trip():
    body = _round_trip("Visit <https://example.com/x> today.")
    assert '<a href="https://example.com/x">https://example.com/x</a>' in body


def test_image_tag_survives_but_sanitizer_drops_src():
    # html_sanitizer._clean_attr strips every img src on purpose: a converted
    # document must not issue attacker-chosen network requests merely by being
    # opened. The <img> and its alt text are what the reader gets.
    body = _round_trip("![A figure](https://example.com/f.png)")
    assert '<img alt="A figure" />' in body
    assert "example.com/f.png" not in body


def test_emphasis_and_inline_code_survive_round_trip():
    body = _round_trip("This is **bold**, *italic*, ~~struck~~ and `x = 1`.")
    assert "<strong>bold</strong>" in body
    assert "<em>italic</em>" in body
    assert "<s>struck</s>" in body
    assert "<code>x = 1</code>" in body


def test_fenced_code_survives_round_trip():
    body = _round_trip("```python\nif a < b:\n    pass\n```\n")
    assert body == "<pre><code>if a &lt; b:\n    pass</code></pre>"


def test_blockquote_and_rule_survive_round_trip():
    body = _round_trip("> quoted\n\n---\n\nafter\n")
    assert "<blockquote><p>quoted</p></blockquote>" in body
    assert "<hr />" in body
    assert "<p>after</p>" in body


def test_deep_headings_survive_round_trip():
    body = _round_trip("#### Four\n\n###### Six\n")
    assert "<h4>Four</h4>" in body
    assert "<h6>Six</h6>" in body


# --- escape-first discipline ---------------------------------------------------


def test_literal_script_prose_stays_escaped():
    markdown = "Prose mentioning <script>alert(1)</script> as text."
    rendered = markdown_to_safe_html(markdown)
    body = sanitize_book_html(rendered)
    assert "<script" not in rendered.lower()
    assert "<script" not in body.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_literal_img_onerror_prose_stays_escaped():
    body = _round_trip('Then <img src=x onerror="alert(1)"> appears in the text.')
    assert "<img" not in body  # no real tag: the only img is escaped prose
    assert '&lt;img src=x onerror="alert(1)"&gt;' in body


def test_javascript_url_in_a_link_is_dropped_by_the_sanitizer():
    # The renderer writes the href it was given; the sanitizer is what refuses
    # the scheme. Both halves of the contract are asserted here.
    rendered = markdown_to_safe_html("[click](javascript:alert)")
    assert '<a href="javascript:alert">' in rendered
    body = sanitize_book_html(rendered)
    assert "javascript:" not in body.lower()
    assert body == "<p><a>click</a></p>"


def test_renderer_output_is_a_fixed_point_of_the_sanitizer():
    markdown = (
        "# Title\n\n"
        "Body with [a link](https://e.com) and **emphasis**.\n\n"
        "| h |\n|---|\n| c |\n\n"
        "- one\n- two\n"
    )
    once = sanitize_book_html(markdown_to_safe_html(markdown))
    assert sanitize_book_html(once) == once
