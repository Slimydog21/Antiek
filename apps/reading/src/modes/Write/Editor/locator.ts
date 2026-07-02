/**
 * Stable locators for the Write block editor (specs/write/ SPR-04 M4).
 *
 * Section/paragraph-level style prompts (SPR-06) and granular edit capture
 * (SPR-02) both anchor to a *stable* address. A raw ProseMirror position
 * is NOT stable — it shifts the moment anything before it changes. So the
 * primary anchor is a per-block `blockId` assigned at creation and carried
 * as a TipTap node attribute, preserved across edits. The positional
 * `paragraphIndex` is only a fallback for resolving a locator whose
 * `blockId` is gone.
 *
 * This module is pure (operates on a plain `EditorBlock[]` abstraction,
 * not a live ProseMirror doc) so locator stability — "the case that
 * bites" — is unit-testable without a browser. `tiptapAdapter.ts` bridges
 * a live editor to this abstraction.
 *
 * The locator maps 1:1 to the backend `EditLocator`
 * (substrate/edit/edit_pair.py): blockId → outline_block_id (for lego
 * blocks) or the paragraph's stable id; paragraphIndex/sentenceIndex are
 * the same ordinals.
 */

export type BlockKindUI = "prose" | "lego";

export interface EditorBlock {
  /** Stable id assigned at creation, preserved across edits. */
  blockId: string;
  /** Plain text of the block (citations stripped for sentence splitting). */
  text: string;
  kind: BlockKindUI;
  /** For lego blocks: the graph node ref (provenance). null for prose. */
  nodeId?: string | null;
  /** For lego blocks migrated/placed: the OutlineBlock id. */
  outlineBlockId?: string | null;
}

export interface BlockLocator {
  sectionId: string;
  /** Primary, stable anchor. */
  blockId: string;
  /** Positional fallback (ordinal within the section). */
  paragraphIndex: number;
  /** Optional sentence ordinal within the block. */
  sentenceIndex?: number;
}

/** Backend EditLocator shape (substrate/edit/edit_pair.py EditLocator). */
export interface BackendLocator {
  deliverable_id: string;
  section_id: string;
  outline_block_id: string | null;
  paragraph_index: number | null;
  sentence_index: number | null;
}

let _counter = 0;

/** Allocate a fresh stable block id. Uses crypto.randomUUID when
 * available; falls back to a monotonic counter (deterministic in tests
 * that stub crypto). */
export function newBlockId(): string {
  const g = globalThis as { crypto?: { randomUUID?: () => string } };
  if (g.crypto?.randomUUID) {
    return `blk-${g.crypto.randomUUID().slice(0, 12)}`;
  }
  _counter += 1;
  return `blk-${_counter.toString(36).padStart(8, "0")}`;
}

/** Build a locator for a block currently at the given index. */
export function locatorForBlock(
  sectionId: string,
  blocks: EditorBlock[],
  blockId: string,
  sentenceIndex?: number,
): BlockLocator | null {
  const idx = blocks.findIndex((b) => b.blockId === blockId);
  if (idx === -1) return null;
  return { sectionId, blockId, paragraphIndex: idx, sentenceIndex };
}

export interface ResolvedBlock {
  block: EditorBlock;
  index: number;
  /** How the locator resolved: stably by id, or via the positional
   * fallback (which means the block was likely edited/replaced). */
  via: "blockId" | "paragraphIndex";
}

/**
 * Resolve a locator against the current blocks. Tries `blockId` first
 * (stable), then `paragraphIndex` (fallback). Returns null when neither
 * resolves — a deleted block surfaces as a clean miss, never a throw.
 */
export function resolveLocator(
  blocks: EditorBlock[],
  locator: BlockLocator,
): ResolvedBlock | null {
  const byId = blocks.findIndex((b) => b.blockId === locator.blockId);
  if (byId !== -1) {
    return { block: blocks[byId], index: byId, via: "blockId" };
  }
  if (
    locator.paragraphIndex >= 0 &&
    locator.paragraphIndex < blocks.length
  ) {
    return {
      block: blocks[locator.paragraphIndex],
      index: locator.paragraphIndex,
      via: "paragraphIndex",
    };
  }
  return null;
}

/**
 * Common abbreviations whose trailing period is not necessarily a sentence
 * boundary. Dot-free forms; deliberately conservative.
 */
const TITLE_ABBREV_SET = new Set(["Dr", "Mr", "Mrs", "Ms", "Prof", "Sr", "Jr"]);
const INLINE_ABBREV_SET = new Set([
  "Inc", "Ltd", "Corp", "Ph",
  "i", "e", "g", // i.e. / e.g. single-letter segments before periods.
  "etc", "vol", "Vol", "p", "pp", "ed", "Ed",
]);

function tokenBeforePeriod(text: string, punctIdx: number): string {
  return text.slice(0, punctIdx).match(/(\b\w+)$/)?.[1] ?? "";
}

function firstContinuationChar(text: string, boundaryEnd: number): string {
  return text.slice(boundaryEnd).trimStart()[0] ?? "";
}

function isDottedInitialismBeforePeriod(text: string, punctIdx: number): boolean {
  return /(?:^|\s)(?:[A-Z]\.)+[A-Z]$/.test(text.slice(0, punctIdx));
}

function isSentenceBoundaryPeriod(text: string, punctIdx: number, boundaryEnd: number): boolean {
  const token = tokenBeforePeriod(text, punctIdx);
  const next = firstContinuationChar(text, boundaryEnd);
  if (punctIdx > 0 && /\d/.test(text[punctIdx - 1])) return false;
  if (isDottedInitialismBeforePeriod(text, punctIdx)) return false;
  if (TITLE_ABBREV_SET.has(token)) return false;
  if (INLINE_ABBREV_SET.has(token) && (next === "" || /[a-z0-9]/.test(next))) {
    return false;
  }
  return true;
}

/**
 * Split a block's text into sentences. Used for sentence-granularity locators
 * and edit capture. Handles common abbreviations (Dr., Mr., U.S., i.e., etc.)
 * and decimal numbers (3.14, €2.50) that the naive `/(?<=[.!?])\s+/` regex
 * would false-split.
 *
 * Strategy: walk every `[.!?]<optional-quote>\s+` boundary candidate, then
 * suppress the split when the period is (a) part of a known abbreviation,
 * (b) part of a multi-period abbreviation (i.e., e.g.), or (c) preceded by a
 * digit (decimal). `!` and `?` always split — they never appear inside
 * abbreviations or numbers.
 */
export function splitIntoSentences(text: string): string[] {
  const parts: string[] = [];
  let last = 0;
  // Match `[.!?]`, optionally followed by a closing quote/bracket, then whitespace.
  const boundaryRe = /[.!?]["')\]]?\s+/g;
  let m: RegExpExecArray | null;
  while ((m = boundaryRe.exec(text)) !== null) {
    const punctIdx = m.index;
    // `!` and `?` are always genuine sentence boundaries.
    if (text[punctIdx] !== ".") {
      parts.push(text.slice(last, m.index + m[0].length).trim());
      last = m.index + m[0].length;
      continue;
    }
    if (!isSentenceBoundaryPeriod(text, punctIdx, m.index + m[0].length)) continue;
    parts.push(text.slice(last, m.index + m[0].length).trim());
    last = m.index + m[0].length;
  }
  const tail = text.slice(last).trim();
  if (tail.length > 0) parts.push(tail);
  return parts.filter((s) => s.length > 0);
}

/** Map a UI locator to the backend EditLocator shape. A lego block's
 * `outlineBlockId` becomes outline_block_id; prose blocks carry null
 * (the paragraph_index is their anchor). */
export function toBackendLocator(
  deliverableId: string,
  locator: BlockLocator,
  block?: EditorBlock,
): BackendLocator {
  return {
    deliverable_id: deliverableId,
    section_id: locator.sectionId,
    outline_block_id: block?.outlineBlockId ?? null,
    paragraph_index: locator.paragraphIndex,
    sentence_index: locator.sentenceIndex ?? null,
  };
}
