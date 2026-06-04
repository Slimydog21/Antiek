import type { Document } from "../../../types/document_model.gen";

/**
 * allBlocksDocument — a fixture exercising EVERY block type and inline span of
 * the SPR-01 document model (SPR-03 M2/rigor #3). One Storybook story + one
 * vitest assertion per block type render against this.
 *
 * It is the SPR-01 round-trip register: heading levels 1–6, a paragraph with
 * strong/emphasis/link/code/inline-math/citation, a nested list, an aligned
 * table whose cells carry markup, a code block, a display-math block (a real
 * arXiv-style equation), a figure with and without a caption, a blockquote, and
 * a footnote. This is "renders in Storybook" — distinct from "renders a real
 * SPR-02 extraction" (rigor #1), which `realArxivMath.ts` covers separately.
 */
export const allBlocksDocument: Document = {
  id: "fixture-all-blocks",
  title: "Every Block Type — a Reader fixture",
  attribution: {
    ip_holder_id: "antiek",
    source_url: null,
    content_class: "platform_authored",
  },
  schema_version: 1,
  blocks: [
    { type: "heading", level: 1, spans: [{ type: "text", text: "Heading level 1" }] },
    { type: "heading", level: 2, spans: [{ type: "text", text: "Heading level 2" }] },
    { type: "heading", level: 3, spans: [{ type: "text", text: "Heading level 3" }] },
    { type: "heading", level: 4, spans: [{ type: "text", text: "Heading level 4" }] },
    { type: "heading", level: 5, spans: [{ type: "text", text: "Heading level 5" }] },
    {
      type: "heading",
      level: 6,
      // inline math inside a heading — an explicit SPR-01 round-trip edge case.
      spans: [
        { type: "text", text: "Heading 6 with inline math " },
        { type: "math", tex: "E = mc^2" },
      ],
    },
    {
      type: "paragraph",
      spans: [
        { type: "text", text: "A paragraph with " },
        { type: "strong", children: [{ type: "text", text: "bold" }] },
        { type: "text", text: ", " },
        { type: "emphasis", children: [{ type: "text", text: "italic" }] },
        { type: "text", text: ", a " },
        {
          type: "link",
          href: "https://arxiv.org/abs/1706.03762",
          children: [{ type: "text", text: "link" }],
        },
        { type: "text", text: ", " },
        { type: "code", text: "inline_code()" },
        { type: "text", text: ", inline math " },
        { type: "math", tex: "\\alpha + \\beta" },
        { type: "text", text: ", and a citation" },
        {
          type: "citation",
          source_document_id: "doc-source-42",
          chunk_id: "chunk-7",
          marker: "[1]",
          char_start: 100,
          char_end: 240,
        },
        { type: "text", text: "." },
      ],
    },
    {
      type: "list",
      ordered: false,
      items: [
        { type: "list_item", blocks: [{ type: "paragraph", spans: [{ type: "text", text: "First item" }] }] },
        {
          type: "list_item",
          blocks: [
            { type: "paragraph", spans: [{ type: "text", text: "Second item, with a nested list:" }] },
            {
              type: "list",
              ordered: true,
              items: [
                { type: "list_item", blocks: [{ type: "paragraph", spans: [{ type: "text", text: "Nested one" }] }] },
                { type: "list_item", blocks: [{ type: "paragraph", spans: [{ type: "text", text: "Nested two" }] }] },
              ],
            },
          ],
        },
      ],
    },
    {
      type: "table",
      alignment: ["left", "center", "right"],
      header: [
        [{ type: "text", text: "Method" }],
        [{ type: "text", text: "Score" }],
        [{ type: "text", text: "Params" }],
      ],
      rows: [
        [
          [{ type: "strong", children: [{ type: "text", text: "Transformer" }] }],
          [{ type: "text", text: "28.4" }],
          [{ type: "text", text: "65M" }],
        ],
        [
          [{ type: "text", text: "Baseline" }, { type: "citation", source_document_id: "doc-source-9", chunk_id: "chunk-1", marker: "[2]" }],
          [{ type: "math", tex: "\\frac{1}{2}" }],
          [{ type: "text", text: "213M" }],
        ],
      ],
    },
    {
      type: "code",
      lang: "python",
      text:
        "def attention(q, k, v):\n    # a deliberately long line to test containment: it should scroll within the block, not widen the reading measure even when it runs well past the comfortable line length\n    return softmax(q @ k.T / sqrt(d_k)) @ v",
    },
    {
      type: "math",
      display: true,
      // a real arXiv-style display equation (the Transformer attention formula).
      tex: "\\mathrm{Attention}(Q, K, V) = \\mathrm{softmax}\\left(\\frac{QK^\\top}{\\sqrt{d_k}}\\right)V",
    },
    {
      type: "figure",
      src: "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Plus_symbol.svg/120px-Plus_symbol.svg.png",
      alt: "A plus symbol",
      caption: [
        { type: "text", text: "Figure 1: a figure " },
        { type: "emphasis", children: [{ type: "text", text: "with" }] },
        { type: "text", text: " a caption." },
      ],
    },
    {
      type: "figure",
      // no src — the raw-PDF case (SPR-01 marks src optional). Honest placeholder.
      alt: "An extracted figure with no resolvable source",
      caption: [],
    },
    {
      type: "blockquote",
      blocks: [
        {
          type: "paragraph",
          spans: [{ type: "text", text: "A blockquote can hold paragraphs and even nested blocks." }],
        },
      ],
    },
    {
      type: "footnote",
      id: "1",
      blocks: [
        {
          type: "paragraph",
          spans: [{ type: "text", text: "A footnote points within this document (a reading convenience), unlike a citation." }],
        },
      ],
    },
  ],
};
