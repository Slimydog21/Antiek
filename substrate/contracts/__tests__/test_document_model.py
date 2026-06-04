"""Round-trip + edge-case tests for the structured document model (Reader SPR-01 M1).

The gate (spec rigor #3): every block and span type serializes and deserializes
without loss. "Looks correct" is not a gate — a green round-trip over the named
edge-case fixtures is. The edge cases enumerated BEFORE the model was written:

* nested lists (a list whose item contains another list),
* a table with column alignment AND an empty cell,
* inline math inside a heading,
* a code block whose text CONTAINS the discriminator string,
* a citation span whose char range crosses a sentence boundary,
* an empty document.

The all-block-types fixture (``arxiv_shaped_document``) is sourced from the
STRUCTURE of a real arXiv paper (title → abstract → sections with display math,
a results table, a figure with caption, inline citations into source documents,
and footnotes) so the schema is validated against real document shape, not a toy.
"""

from __future__ import annotations

import pytest

from substrate.contracts.document_model import (
    DOCUMENT_MODEL_SCHEMA_VERSION,
    BlockquoteBlock,
    CitationSpan,
    CodeBlock,
    CodeSpan,
    Document,
    DocumentAttribution,
    EmphasisSpan,
    FigureBlock,
    FootnoteBlock,
    HeadingBlock,
    LinkSpan,
    ListBlock,
    ListItem,
    MathBlock,
    MathSpan,
    ParagraphBlock,
    StrongSpan,
    TableBlock,
    TextSpan,
)


# ───────────────────────────────────────────────────────────────────────────
# The all-block-types fixture, shaped like a real arXiv paper.
# ───────────────────────────────────────────────────────────────────────────


def arxiv_shaped_document() -> Document:
    """A Document exercising EVERY block and span type, shaped like a real
    arXiv paper. Returned by a function (not a module constant) so each test
    gets a fresh, independent instance."""
    return Document(
        id="arxiv:2310.00001",
        title="On the Convergence of Structured Readers",
        attribution=DocumentAttribution(
            ip_holder_id="arXiv",
            source_url="https://arxiv.org/abs/2310.00001",
            content_class="source_declared_open",
        ),
        blocks=[
            # H1 with inline math inside the heading (edge case).
            HeadingBlock(
                level=1,
                spans=[
                    TextSpan(text="Bounding "),
                    MathSpan(tex="\\epsilon"),
                    TextSpan(text="-error"),
                ],
            ),
            # Abstract paragraph with strong, emphasis, link, inline code, and a
            # citation span whose char range crosses a sentence boundary.
            HeadingBlock(level=2, spans=[TextSpan(text="Abstract")]),
            ParagraphBlock(
                spans=[
                    StrongSpan(children=[TextSpan(text="We show")]),
                    TextSpan(text=" that "),
                    EmphasisSpan(children=[TextSpan(text="every")]),
                    TextSpan(text=" renderer converges. See "),
                    LinkSpan(
                        href="https://example.org/prior",
                        children=[TextSpan(text="prior work")],
                    ),
                    TextSpan(text=" and the "),
                    CodeSpan(text="render_region"),
                    TextSpan(text=" API. "),
                    # Citation char range crosses a sentence boundary in the
                    # SOURCE document (start mid-sentence, end in the next).
                    CitationSpan(
                        source_document_id="arxiv:2009.12345",
                        chunk_id="chunk-0007",
                        marker="[1]",
                        char_start=412,
                        char_end=589,
                    ),
                ],
            ),
            # A section with a display-math block (multi-line tex).
            HeadingBlock(level=2, spans=[TextSpan(text="Method")]),
            ParagraphBlock(spans=[TextSpan(text="The loss is defined as:")]),
            MathBlock(
                display=True,
                tex="\\mathcal{L} = \\sum_{i=1}^{n}\n  \\| f(x_i) - y_i \\|^2",
            ),
            # A nested, ordered list whose item holds a paragraph AND a nested
            # unordered list with a code block inside (deep nesting edge case).
            ListBlock(
                ordered=True,
                items=[
                    ListItem(
                        blocks=[
                            ParagraphBlock(spans=[TextSpan(text="Extract blocks.")]),
                            ListBlock(
                                ordered=False,
                                items=[
                                    ListItem(
                                        blocks=[
                                            ParagraphBlock(
                                                spans=[TextSpan(text="Then run:")]
                                            ),
                                            CodeBlock(
                                                lang="python",
                                                text="Document.model_validate(d)",
                                            ),
                                        ]
                                    )
                                ],
                            ),
                        ]
                    ),
                    ListItem(blocks=[ParagraphBlock(spans=[TextSpan(text="Serve.")])]),
                ],
            ),
            # A results table with per-column alignment AND an empty cell.
            HeadingBlock(level=2, spans=[TextSpan(text="Results")]),
            TableBlock(
                alignment=["left", "center", "right"],
                header=[
                    [TextSpan(text="Model")],
                    [TextSpan(text="Acc")],
                    [TextSpan(text="Notes")],
                ],
                rows=[
                    [
                        [TextSpan(text="Ours")],
                        [TextSpan(text="0.98")],
                        # Empty cell (edge case): an empty span list.
                        [],
                    ],
                    [
                        [TextSpan(text="Baseline")],
                        [TextSpan(text="0.91")],
                        # A cell carrying a citation span (rich cell content).
                        [
                            CitationSpan(
                                source_document_id="arxiv:1900.00000",
                                chunk_id="chunk-table",
                                marker="(B)",
                            )
                        ],
                    ],
                ],
            ),
            # A figure with caption spans; src/alt present here.
            FigureBlock(
                src="https://arxiv.org/figs/2310.00001/fig1.png",
                alt="convergence curve",
                caption=[
                    TextSpan(text="Figure 1. Error vs. steps. "),
                    EmphasisSpan(children=[TextSpan(text="Lower is better.")]),
                ],
            ),
            # A figure with NO src and NO alt (the optional-fields edge case
            # SPR-02 must confirm against a real extraction).
            FigureBlock(
                caption=[TextSpan(text="Figure 2. Caption recovered without src.")]
            ),
            # A blockquote containing a nested paragraph + list.
            BlockquoteBlock(
                blocks=[
                    ParagraphBlock(spans=[TextSpan(text="As noted previously,")]),
                    ListBlock(
                        items=[
                            ListItem(blocks=[ParagraphBlock(spans=[TextSpan(text="point one")])])
                        ]
                    ),
                ]
            ),
            # A code block whose TEXT contains the discriminator string — must
            # round-trip unharmed (not be re-parsed as a block).
            CodeBlock(
                lang="json",
                text='{"type": "paragraph", "spans": [{"type": "text", "text": "x"}]}',
            ),
            # A footnote definition (distinct from a citation).
            FootnoteBlock(
                id="1",
                blocks=[ParagraphBlock(spans=[TextSpan(text="A clarifying footnote.")])],
            ),
        ],
    )


# ───────────────────────────────────────────────────────────────────────────
# The core gate: round-trip byte-identity.
# ───────────────────────────────────────────────────────────────────────────


def test_full_document_round_trips_byte_identical():
    """``Document.model_validate(doc.model_dump())`` is identical for a fixture
    exercising every block and span type. THE gate (rigor #3)."""
    doc = arxiv_shaped_document()
    dumped = doc.model_dump()
    reparsed = Document.model_validate(dumped)
    assert reparsed.model_dump() == dumped


def test_full_document_round_trips_through_json():
    """JSON serialization (the wire format the Reader actually receives) also
    round-trips — discriminator-by-``type`` survives a string trip."""
    doc = arxiv_shaped_document()
    as_json = doc.model_dump_json()
    reparsed = Document.model_validate_json(as_json)
    assert reparsed.model_dump_json() == as_json


def test_fixture_actually_uses_every_block_type():
    """Guard against the fixture silently dropping a block type as the model
    evolves: assert all nine block discriminators appear somewhere in the tree."""
    doc = arxiv_shaped_document()
    seen: set[str] = set()

    def walk_blocks(blocks):
        for b in blocks:
            seen.add(b.type)
            if b.type == "list":
                for item in b.items:
                    walk_blocks(item.blocks)
            elif b.type == "blockquote":
                walk_blocks(b.blocks)
            elif b.type == "footnote":
                walk_blocks(b.blocks)

    walk_blocks(doc.blocks)
    assert seen == {
        "heading",
        "paragraph",
        "list",
        "table",
        "code",
        "math",
        "figure",
        "blockquote",
        "footnote",
    }


def test_fixture_actually_uses_every_span_type():
    """Assert all seven inline-span discriminators appear somewhere."""
    doc = arxiv_shaped_document()
    seen: set[str] = set()

    def walk_spans(spans):
        for s in spans:
            seen.add(s.type)
            if s.type in ("strong", "emphasis", "link"):
                walk_spans(s.children)

    def walk_blocks(blocks):
        for b in blocks:
            if b.type in ("heading", "paragraph"):
                walk_spans(b.spans)
            elif b.type == "figure":
                walk_spans(b.caption)
            elif b.type == "table":
                for cell in b.header:
                    walk_spans(cell)
                for row in b.rows:
                    for cell in row:
                        walk_spans(cell)
            elif b.type == "list":
                for item in b.items:
                    walk_blocks(item.blocks)
            elif b.type in ("blockquote", "footnote"):
                walk_blocks(b.blocks)

    walk_blocks(doc.blocks)
    assert seen == {"text", "strong", "emphasis", "link", "code", "math", "citation"}


# ───────────────────────────────────────────────────────────────────────────
# Named edge-case fixtures (rigor #3 — each its own fixture).
# ───────────────────────────────────────────────────────────────────────────


def _roundtrips(doc: Document) -> bool:
    return Document.model_validate(doc.model_dump()).model_dump() == doc.model_dump()


def test_empty_document_round_trips():
    doc = Document(id="empty", title="")
    assert doc.blocks == []
    assert doc.toc() == []
    assert _roundtrips(doc)


def test_nested_lists_round_trip():
    doc = Document(
        id="nl",
        title="nested",
        blocks=[
            ListBlock(
                ordered=False,
                items=[
                    ListItem(
                        blocks=[
                            ParagraphBlock(spans=[TextSpan(text="outer")]),
                            ListBlock(
                                items=[
                                    ListItem(
                                        blocks=[ParagraphBlock(spans=[TextSpan(text="inner")])]
                                    )
                                ]
                            ),
                        ]
                    )
                ],
            )
        ],
    )
    assert _roundtrips(doc)
    # The nested list is genuinely a ListBlock inside a ListItem.
    inner = doc.blocks[0].items[0].blocks[1]
    assert isinstance(inner, ListBlock)


def test_table_with_alignment_and_empty_cell_round_trips():
    doc = Document(
        id="tbl",
        title="t",
        blocks=[
            TableBlock(
                alignment=["left", None, "right"],
                header=[[TextSpan(text="a")], [TextSpan(text="b")], [TextSpan(text="c")]],
                rows=[[[TextSpan(text="1")], [], [TextSpan(text="3")]]],
            )
        ],
    )
    assert _roundtrips(doc)
    table = doc.blocks[0]
    assert table.alignment == ["left", None, "right"]
    assert table.rows[0][1] == []  # the empty cell survived


def test_inline_math_inside_heading_round_trips():
    doc = Document(
        id="h",
        title="h",
        blocks=[
            HeadingBlock(
                level=3,
                spans=[TextSpan(text="The "), MathSpan(tex="O(n\\log n)"), TextSpan(text=" bound")],
            )
        ],
    )
    assert _roundtrips(doc)
    # And the ToC label flattens the inline math into the heading text.
    toc = doc.toc()
    assert toc[0].text == "The O(n\\log n) bound"
    assert toc[0].level == 3


def test_code_block_containing_discriminator_string_round_trips():
    payload = '{"type": "table", "rows": []}'
    doc = Document(
        id="c",
        title="c",
        blocks=[CodeBlock(lang="json", text=payload)],
    )
    assert _roundtrips(doc)
    # The text was NOT re-parsed into a TableBlock — it is still a code block.
    block = doc.blocks[0]
    assert isinstance(block, CodeBlock)
    assert block.text == payload


def test_citation_span_crossing_sentence_boundary_round_trips():
    doc = Document(
        id="cite",
        title="cite",
        blocks=[
            ParagraphBlock(
                spans=[
                    TextSpan(text="Prior work "),
                    CitationSpan(
                        source_document_id="src-doc",
                        chunk_id="src-chunk",
                        marker="[7]",
                        char_start=100,  # mid-sentence in the source
                        char_end=260,  # past the sentence boundary in the source
                    ),
                ]
            )
        ],
    )
    assert _roundtrips(doc)
    span = doc.blocks[0].spans[1]
    assert isinstance(span, CitationSpan)
    assert span.char_start == 100 and span.char_end == 260


# ───────────────────────────────────────────────────────────────────────────
# Discriminator + reuse + derivation invariants.
# ───────────────────────────────────────────────────────────────────────────


def test_discriminator_selects_the_right_block_type():
    """Validating from a raw dict (the ingest/serve wire shape) selects the
    member by ``type`` — the discriminated union works without Python types."""
    doc = Document.model_validate(
        {
            "id": "raw",
            "title": "raw",
            "blocks": [
                {"type": "heading", "level": 1, "spans": [{"type": "text", "text": "H"}]},
                {
                    "type": "paragraph",
                    "spans": [
                        {
                            "type": "citation",
                            "source_document_id": "s",
                            "chunk_id": "k",
                            "marker": "[1]",
                        }
                    ],
                },
            ],
        }
    )
    assert isinstance(doc.blocks[0], HeadingBlock)
    assert isinstance(doc.blocks[1], ParagraphBlock)
    assert isinstance(doc.blocks[1].spans[0], CitationSpan)


def test_unknown_field_is_rejected_not_silently_dropped():
    """``extra='forbid'`` — an unknown field is a loud failure, so a typo in a
    block never silently round-trips as a dropped key."""
    with pytest.raises(Exception):
        Document.model_validate(
            {
                "id": "x",
                "title": "x",
                "blocks": [{"type": "paragraph", "spans": [], "bogus_field": 1}],
            }
        )


def test_citation_is_a_span_not_a_block():
    """A citation is a first-class INLINE span (carrying the provenance triple),
    not a block and not a footnote — the load-bearing schema decision."""
    cite = CitationSpan(source_document_id="s", chunk_id="k", marker="[1]")
    assert cite.type == "citation"
    assert cite.source_document_id == "s" and cite.chunk_id == "k"
    # It is NOT a FootnoteBlock and NOT a LinkSpan.
    assert not hasattr(cite, "href")
    assert not hasattr(cite, "blocks")


def test_content_class_reuses_servable_vocabulary():
    """``content_class`` is typed against the §9.0 ``ContentClass`` Literal
    owned by ``servable.py`` — a value outside that vocabulary is rejected,
    proving reuse (not a parallel free-form string)."""
    from substrate.contracts.servable import ContentClass  # noqa: F401

    ok = DocumentAttribution(content_class="public_domain")
    assert ok.content_class == "public_domain"
    with pytest.raises(Exception):
        DocumentAttribution(content_class="not_a_real_class")


def test_toc_is_derived_not_stored():
    """There is no ``toc`` field on Document; it is derived from headings.
    A second stored copy could drift — derive-don't-duplicate."""
    assert "toc" not in Document.model_fields
    doc = Document(
        id="t",
        title="t",
        blocks=[
            HeadingBlock(level=1, spans=[TextSpan(text="One")]),
            ParagraphBlock(spans=[TextSpan(text="body")]),
            HeadingBlock(level=2, spans=[TextSpan(text="Two")]),
        ],
    )
    toc = doc.toc()
    assert [(e.level, e.text, e.block_index) for e in toc] == [
        (1, "One", 0),
        (2, "Two", 2),
    ]


def test_schema_version_present_and_defaulted():
    doc = Document(id="v", title="v")
    assert doc.schema_version == DOCUMENT_MODEL_SCHEMA_VERSION == 1
    # A document loaded under an explicit older version keeps it.
    older = Document.model_validate({"id": "v", "title": "v", "schema_version": 0, "blocks": []})
    assert older.schema_version == 0
