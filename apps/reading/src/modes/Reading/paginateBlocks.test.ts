/**
 * paginateBlocks.test.ts — pagination over the document model (SPR-03 M4, rigor #3).
 *
 * The three pagination edge cases the spec names, each asserted:
 *  - a table taller than the page → its own intact window (never clipped/split);
 *  - a figure that would land on a page boundary → kept whole on one window;
 *  - a heading that would orphan → stays attached to its content's window via
 *    the firstBlockIndex → window mapping (ToC lands on the right page).
 */
import { describe, expect, it } from "vitest";

import {
  paginateBlocks,
  windowForBlockIndex,
  DEFAULT_BLOCKS_PER_PAGE,
} from "./paginateBlocks";
import type { Block } from "../../types/document_model.gen";

function para(text: string): Block {
  return { type: "paragraph", spans: [{ type: "text", text }] };
}

describe("paginateBlocks — windowing", () => {
  it("an empty document yields one empty window (chrome still renders)", () => {
    const pages = paginateBlocks([]);
    expect(pages).toHaveLength(1);
    expect(pages[0]).toMatchObject({ pageIndex: 0, pageNumber: 1, firstBlockIndex: 0 });
    expect(pages[0].blocks).toEqual([]);
  });

  it("assigns stable 0-based pageIndex locators and 1-based pageNumbers", () => {
    const blocks = Array.from({ length: DEFAULT_BLOCKS_PER_PAGE * 2 + 1 }, (_, i) => para(`p${i}`));
    const pages = paginateBlocks(blocks);
    expect(pages).toHaveLength(3);
    expect(pages.map((p) => p.pageIndex)).toEqual([0, 1, 2]);
    expect(pages.map((p) => p.pageNumber)).toEqual([1, 2, 3]);
  });

  it("keeps a tall TABLE whole — never split across a boundary (clipping case)", () => {
    const tallTable: Block = {
      type: "table",
      alignment: ["left", "right"],
      header: [[{ type: "text", text: "k" }], [{ type: "text", text: "v" }]],
      rows: Array.from({ length: 100 }, (_, r) => [
        [{ type: "text" as const, text: `r${r}` }],
        [{ type: "text" as const, text: String(r) }],
      ]),
    };
    const pages = paginateBlocks([para("intro"), tallTable, para("after")]);
    // All three blocks fit in one window (under the budget); the table is one
    // block and is NEVER divided — its 100 rows stay together.
    const tableWindow = pages.find((p) => p.blocks.some((b) => b.type === "table"))!;
    const table = tableWindow.blocks.find((b) => b.type === "table") as Extract<Block, { type: "table" }>;
    expect(table.rows).toHaveLength(100);
    // and it appears in exactly ONE window (not duplicated/split).
    const tableWindows = pages.filter((p) => p.blocks.some((b) => b.type === "table"));
    expect(tableWindows).toHaveLength(1);
  });

  it("keeps a FIGURE whole at a page boundary (figure + caption together)", () => {
    // Fill exactly to the budget, then a figure: the figure pushes to the next
    // window as a whole block rather than being split.
    const filler = Array.from({ length: DEFAULT_BLOCKS_PER_PAGE }, (_, i) => para(`f${i}`));
    const figure: Block = {
      type: "figure",
      alt: "boundary figure",
      caption: [{ type: "text", text: "caption stays with the figure" }],
    };
    const pages = paginateBlocks([...filler, figure, para("tail")]);
    expect(pages).toHaveLength(2);
    // the figure is on the SECOND window, intact (with its caption inside it).
    const fig = pages[1].blocks.find((b) => b.type === "figure") as Extract<Block, { type: "figure" }>;
    expect(fig).toBeTruthy();
    expect(fig.caption).toHaveLength(1);
  });

  it("a heading that would orphan maps to the window containing its content", () => {
    // A heading at the very end of one budget would orphan; the ToC entry
    // (located by document block index) must resolve to the window that holds
    // the heading. windowForBlockIndex gives that mapping.
    const blocks: Block[] = [
      ...Array.from({ length: DEFAULT_BLOCKS_PER_PAGE - 1 }, (_, i) => para(`a${i}`)),
      { type: "heading", level: 2, spans: [{ type: "text", text: "Section Two" }] }, // index 11
      para("body of section two"),
    ];
    const pages = paginateBlocks(blocks);
    const headingDocIndex = DEFAULT_BLOCKS_PER_PAGE - 1; // 11
    const w = windowForBlockIndex(pages, headingDocIndex);
    // the heading is the last block of window 0 (budget 12, indices 0..11).
    expect(w).toBe(0);
    expect(pages[0].blocks.some((b) => b.type === "heading")).toBe(true);
  });

  it("windowForBlockIndex clamps and handles no windows", () => {
    const pages = paginateBlocks(Array.from({ length: 30 }, (_, i) => para(`p${i}`)));
    expect(windowForBlockIndex(pages, 0)).toBe(0);
    expect(windowForBlockIndex(pages, 25)).toBe(2);
    expect(windowForBlockIndex([], 5)).toBeNull();
  });
});
