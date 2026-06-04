"""Round-trip + edge-case tests for the text/markdown → Document extractor (SPR-02 M1).

The gate (spec rigor #3): the extractor produces blocks that validate against the
SPR-01 schema, round-trip through JSON, and the ENUMERATED edge cases each pass
(or carry a documented degradation). "Looks correct" is not a gate; a green
round-trip over the named fixtures is.

Edge cases enumerated BEFORE coding (rigor #3), each a test below:
  * inline math inside a heading      → MathSpan in the heading's spans
  * nested lists                      → ListBlock whose item holds a ListBlock
  * table with alignment + empty cell → per-column alignment + an empty ([]) cell
  * fenced code containing the model's discriminator string → verbatim CodeBlock
  * a dollar sign INSIDE a code block  → kept literal, not parsed as math
  * blockquote with nested content     → BlockquoteBlock with inner blocks
  * a link + strong + emphasis nest    → nested children spans
  * plain text (no markdown)           → degrades to ParagraphBlocks (M5 backfill)
"""

from __future__ import annotations

from substrate.contracts.document_model import Document
from processing.extraction.to_document_model import (
    markdown_to_blocks,
    text_to_document,
)


def _roundtrips(doc: Document) -> bool:
    """A Document round-trips byte-identical through JSON (the wire format the
    Reader receives). The SPR-01 core gate, reused here on extractor output."""
    as_json = doc.model_dump_json()
    reparsed = Document.model_validate_json(as_json)
    return reparsed.model_dump_json() == as_json


# ───────────────────────────────────────────────────────────────────────────
# Core: every block type extracts and round-trips.
# ───────────────────────────────────────────────────────────────────────────


_EVERY_BLOCK_MD = """\
# Top Heading with $x^2$ inline

A paragraph with **bold**, *emphasis*, a [link](https://example.org), `code`,
and inline math $a+b$.

## Second level

> A blockquote.
>
> - quoted item

1. first
   - nested bullet
   - second nested
2. second

| Name | Value | Note |
|:-----|:-----:|-----:|
| a    | 1     |      |
| b    | 2     | x    |

```python
d = {"type": "paragraph", "spans": [{"type": "text", "text": "$keep me$"}]}
```

$$
E = mc^2
$$
"""


def test_every_block_type_extracts_and_round_trips():
    doc = text_to_document(_EVERY_BLOCK_MD, document_id="doc-test-1")
    assert _roundtrips(doc)
    kinds = {b.type for b in doc.blocks}
    # heading, paragraph, blockquote, list, table, code, math present.
    assert {"heading", "paragraph", "blockquote", "list", "table", "code", "math"} <= kinds


def test_validates_against_spr01_schema():
    """Every emitted block validates against the pinned SPR-01 contract — a
    re-validate of the dumped model raises nothing."""
    doc = text_to_document(_EVERY_BLOCK_MD, document_id="doc-test-2")
    Document.model_validate(doc.model_dump())  # raises on any schema violation


def test_title_falls_back_to_first_h1():
    doc = text_to_document(_EVERY_BLOCK_MD, document_id="doc-test-3")
    assert doc.title == "Top Heading with x^2 inline"  # math contributes its tex


# ───────────────────────────────────────────────────────────────────────────
# Edge case: inline math inside a heading is a MathSpan, not literal $x$.
# ───────────────────────────────────────────────────────────────────────────


def test_inline_math_in_heading_is_a_math_span():
    blocks = markdown_to_blocks("# Bound the $\\epsilon$-error\n")
    heading = blocks[0]
    assert heading.type == "heading"
    span_types = [s.type for s in heading.spans]
    assert "math" in span_types
    math_span = next(s for s in heading.spans if s.type == "math")
    assert math_span.tex == "\\epsilon"
    # The literal dollar string must NOT survive as text.
    text_blob = "".join(s.text for s in heading.spans if s.type == "text")
    assert "$" not in text_blob


def test_inline_math_in_paragraph_is_a_math_span():
    blocks = markdown_to_blocks("The value $x^2 + 1$ is positive.\n")
    para = blocks[0]
    assert para.type == "paragraph"
    assert any(s.type == "math" and s.tex == "x^2 + 1" for s in para.spans)


# ───────────────────────────────────────────────────────────────────────────
# Edge case: nested lists.
# ───────────────────────────────────────────────────────────────────────────


def test_nested_lists():
    md = "1. outer\n   - inner a\n   - inner b\n2. outer two\n"
    blocks = markdown_to_blocks(md)
    lst = blocks[0]
    assert lst.type == "list" and lst.ordered is True
    first_item = lst.items[0]
    nested = [b for b in first_item.blocks if b.type == "list"]
    assert nested, "the first item should contain a nested list"
    assert nested[0].ordered is False


# ───────────────────────────────────────────────────────────────────────────
# Edge case: table with alignment + an empty cell.
# ───────────────────────────────────────────────────────────────────────────


def test_table_alignment_and_empty_cell():
    md = "| L | C | R |\n|:--|:-:|--:|\n| 1 |   | 3 |\n"
    blocks = markdown_to_blocks(md)
    table = blocks[0]
    assert table.type == "table"
    assert table.alignment == ["left", "center", "right"]
    # The middle body cell is empty → an empty span list, not a dropped cell.
    assert len(table.rows) == 1
    assert table.rows[0][1] == []
    assert len(table.rows[0]) == 3  # three columns preserved


# ───────────────────────────────────────────────────────────────────────────
# Edge case: fenced code containing the discriminator string + a dollar sign.
# ───────────────────────────────────────────────────────────────────────────


def test_code_block_preserves_discriminator_and_dollar_verbatim():
    body = '{"type": "paragraph", "x": "$not math$"}'
    md = f"```json\n{body}\n```\n"
    blocks = markdown_to_blocks(md)
    code = blocks[0]
    assert code.type == "code"
    assert code.lang == "json"
    assert code.text == body  # verbatim — not re-parsed, dollar kept literal
    # And it round-trips even though the body contains the model's own keys.
    doc = text_to_document(md, document_id="doc-code")
    assert _roundtrips(doc)


# ───────────────────────────────────────────────────────────────────────────
# Edge case: blockquote with nested content.
# ───────────────────────────────────────────────────────────────────────────


def test_blockquote_with_nested_blocks():
    md = "> A quote.\n>\n> - item one\n> - item two\n"
    blocks = markdown_to_blocks(md)
    bq = blocks[0]
    assert bq.type == "blockquote"
    inner_kinds = {b.type for b in bq.blocks}
    assert "paragraph" in inner_kinds
    assert "list" in inner_kinds


# ───────────────────────────────────────────────────────────────────────────
# Edge case: nested inline markup (strong wrapping emphasis + a link).
# ───────────────────────────────────────────────────────────────────────────


def test_nested_inline_markup():
    blocks = markdown_to_blocks("This is **bold with *italic* inside** and a [link](http://x).\n")
    para = blocks[0]
    strong = next(s for s in para.spans if s.type == "strong")
    assert any(c.type == "emphasis" for c in strong.children)
    link = next(s for s in para.spans if s.type == "link")
    assert link.href == "http://x"


# ───────────────────────────────────────────────────────────────────────────
# Plain text (no markdown) degrades to paragraphs — the M5 backfill path.
# ───────────────────────────────────────────────────────────────────────────


def test_plain_text_degrades_to_paragraphs():
    text = "First paragraph of plain text.\n\nSecond paragraph here.\n"
    doc = text_to_document(text, document_id="doc-plain")
    para_blocks = [b for b in doc.blocks if b.type == "paragraph"]
    assert len(para_blocks) == 2
    assert _roundtrips(doc)


def test_empty_body_is_valid_empty_document():
    doc = text_to_document("", document_id="doc-empty")
    assert doc.blocks == []
    assert _roundtrips(doc)
