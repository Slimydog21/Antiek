import type { Block } from "../../types/document_model.gen";

/**
 * paginateBlocks — pagination over the structured document model (SPR-03 M4).
 *
 * The legacy `paginate.ts` paginates a TEXT string on `## Page N` markers — the
 * locator the whole Read workflow (TOC jumps, ad slots, voice notes) keyed off.
 * This sprint renders BLOCKS, not text, so pagination must window over blocks.
 *
 * The contract this preserves (rigor #4 — read paginate.ts before replacing):
 *  - a stable 0-based `pageIndex` locator per window (the same anchor TOC jumps,
 *    ad slots, and voice notes use);
 *  - a `pageNumber` (1-based) for display;
 *  - whole blocks per window — a table or a figure is NEVER split across a page
 *    boundary (the acceptance: "pagination handles a table and a figure without
 *    clipping"). We page on a block-COUNT budget, not a character/line budget,
 *    precisely so an oversized block (a tall table) stays intact: it occupies
 *    its window without being cut. A block taller than the budget is a window of
 *    its own rather than clipped — the honest degrade.
 *  - each window carries the `firstBlockIndex` (its first block's index in the
 *    full `blocks` array) so the ToC — derived from heading blocks by their
 *    block index — can map a heading to the page that contains it.
 *
 * Why block-count and not measured height: pagination here is content-derived
 * and deterministic (the same property paginate.ts holds — "never tied to
 * scroll offset or viewport height"). A height-measured paginator would need
 * layout (jsdom has none → untestable) and would re-page on every resize. A
 * block-budget paginator is deterministic, testable, and keeps blocks whole.
 * The budget is a readable-page heuristic, tunable without touching the locator
 * contract.
 */

/** Blocks per page window. A heuristic for a comfortable reading page; chosen
 *  so a normal mix of paragraphs/headings fills a screen without a long scroll,
 *  while an oversized block (tall table) still gets its own intact window. */
export const DEFAULT_BLOCKS_PER_PAGE = 12;

export interface BlockPageWindow {
  /** 0-based page index — the canonical locator (same role as paginate.ts). */
  pageIndex: number;
  /** 1-based page number shown to the reader. */
  pageNumber: number;
  /** The blocks on this page (whole, never clipped). */
  blocks: Block[];
  /** The index, in the FULL document `blocks` array, of this window's first
   *  block — so a ToC heading (located by its document block index) maps to the
   *  window that contains it. */
  firstBlockIndex: number;
}

/**
 * Split a document's blocks into page windows of at most `blocksPerPage` whole
 * blocks. An empty document yields a single empty window (so the reader still
 * renders its chrome rather than nothing — the same "always a window" guarantee
 * paginate.ts gives a gated snippet).
 */
export function paginateBlocks(
  blocks: Block[],
  blocksPerPage: number = DEFAULT_BLOCKS_PER_PAGE,
): BlockPageWindow[] {
  const budget = Math.max(1, blocksPerPage);
  if (blocks.length === 0) {
    return [{ pageIndex: 0, pageNumber: 1, blocks: [], firstBlockIndex: 0 }];
  }
  const windows: BlockPageWindow[] = [];
  for (let i = 0; i < blocks.length; i += budget) {
    const pageIndex = windows.length;
    windows.push({
      pageIndex,
      pageNumber: pageIndex + 1,
      blocks: blocks.slice(i, i + budget),
      firstBlockIndex: i,
    });
  }
  return windows;
}

/**
 * Map a document block index (e.g. a ToC heading's `block_index`) to the page
 * window that contains it. Returns the 0-based window index, clamped into range,
 * or null when there are no windows.
 */
export function windowForBlockIndex(
  windows: BlockPageWindow[],
  blockIndex: number,
): number | null {
  if (windows.length === 0) return null;
  // Find the last window whose firstBlockIndex is <= blockIndex.
  let target = 0;
  for (let w = 0; w < windows.length; w++) {
    if (windows[w].firstBlockIndex <= blockIndex) target = w;
    else break;
  }
  return target;
}
