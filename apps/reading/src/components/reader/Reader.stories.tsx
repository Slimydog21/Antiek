import type { Meta, StoryObj } from "@storybook/react";

import Reader from "./Reader";
import type { ReaderProps } from "./Reader";
import { allBlocksDocument } from "./fixtures/allBlocks";
import { arxivMathDocument } from "./fixtures/arxivMath";
import { paginateBlocks } from "../../modes/Reading/paginateBlocks";
import type { Document } from "../../types/document_model.gen";

/**
 * The one <Reader> — renders the SPR-01 typed-block document model with full
 * typographic fidelity (SPR-03). These stories are the M2 acceptance surface:
 * EVERY block type renders correctly — **bold** is bold, an aligned table is a
 * real <table>, $$math$$ is typeset, code is contained.
 *
 * Honesty (rigor #1): these stories render FIXTURES, not a real SPR-02
 * extraction. They prove the renderer is correct over the model; the handoff
 * states what was verified against a real paper (the math-degrade cases here
 * use real arXiv-style TeX).
 */
const meta = {
  title: "Reader / The one Reader",
  component: Reader,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof Reader>;

export default meta;
type Story = StoryObj<typeof meta>;

function framed(args: ReaderProps) {
  return (
    <div className="bg-ice-0 dark:bg-charcoal-2 p-8 max-w-2xl mx-auto min-h-screen">
      <Reader {...args} />
    </div>
  );
}

/** Every block type + every inline span in one document. The headline story. */
export const EveryBlockType: Story = {
  args: { document: allBlocksDocument, assetId: allBlocksDocument.id },
  render: (args) => framed(args),
};

/** Night register — the same document on the dark surface ramp. */
export const Night: Story = {
  args: { document: allBlocksDocument, assetId: allBlocksDocument.id },
  render: (args) => (
    <div className="dark">
      <div className="bg-charcoal-2 p-8 max-w-2xl mx-auto min-h-screen">
        <Reader {...args} />
      </div>
    </div>
  ),
};

/** Real arXiv-style math: the supported equations typeset; the unsupported ones
 *  degrade to a VISIBLE fenced-tex fallback (rigor #1) — never blank, never a
 *  crash. */
export const ArxivMath: Story = {
  args: { document: arxivMathDocument, assetId: arxivMathDocument.id },
  render: (args) => framed(args),
};

// ── Pagination edge cases (rigor #3): each its own story ─────────────────────

const tallTableDoc: Document = {
  id: "fx-tall-table",
  title: "A table taller than a page",
  blocks: [
    { type: "heading", level: 2, spans: [{ type: "text", text: "A very tall table" }] },
    {
      type: "table",
      alignment: ["left", "right"],
      header: [[{ type: "text", text: "Row" }], [{ type: "text", text: "Value" }]],
      rows: Array.from({ length: 40 }, (_, r) => [
        [{ type: "text" as const, text: `row ${r + 1}` }],
        [{ type: "text" as const, text: String((r + 1) * 7) }],
      ]),
    },
  ],
};

/** A table taller than the page budget stays a WHOLE block on its own window —
 *  it is never clipped or cut across a boundary (acceptance: pagination handles
 *  a table without clipping). */
export const PaginationTallTable: Story = {
  args: { document: tallTableDoc },
  render: (args) => {
    const pages = paginateBlocks(args.document.blocks ?? []);
    return (
      <div className="bg-ice-0 dark:bg-charcoal-2 p-8 max-w-2xl mx-auto">
        <p className="font-mono text-xs text-ink-mute mb-3">
          {pages.length} page window(s); the tall table is intact on its window.
        </p>
        <Reader {...args} blocks={pages[0].blocks} />
      </div>
    );
  },
};

const figureBoundaryDoc: Document = {
  id: "fx-figure-boundary",
  title: "A figure at a page boundary",
  blocks: [
    ...Array.from({ length: 11 }, (_, i) => ({
      type: "paragraph" as const,
      spans: [{ type: "text" as const, text: `Filler paragraph ${i + 1}.` }],
    })),
    {
      type: "figure",
      src: undefined,
      alt: "A figure that would land on a page boundary",
      caption: [{ type: "text", text: "Figure at the boundary — kept whole." }],
    },
    { type: "paragraph", spans: [{ type: "text", text: "Trailing paragraph." }] },
  ],
};

/** A figure that would land exactly on a page boundary is pushed WHOLE to the
 *  next window — never split (the figure + its caption stay together). */
export const PaginationFigureAtBoundary: Story = {
  args: { document: figureBoundaryDoc },
  render: (args) => {
    const pages = paginateBlocks(args.document.blocks ?? []);
    return (
      <div className="bg-ice-0 dark:bg-charcoal-2 p-8 max-w-2xl mx-auto">
        <p className="font-mono text-xs text-ink-mute mb-3">
          {pages.length} windows; the figure is whole on whichever window holds it.
        </p>
        {pages.map((p) => (
          <div key={p.pageIndex} className="border-b-2 border-dashed border-rule pb-6 mb-6">
            <p className="font-mono text-[10px] text-ink-mute mb-2">page {p.pageNumber}</p>
            <Reader {...args} blocks={p.blocks} />
          </div>
        ))}
      </div>
    );
  },
};
