/**
 * selectionCharRange — resolve a selection's BLOCK-RELATIVE char offsets
 * (antiek-reader SPR-06, M3).
 *
 * The SPR-01 ``Region`` anchors a Dialogue thread by ``char_start`` /
 * ``char_end`` measured INTO THE BLOCK'S OWN TEXT (0-based) — NOT the whole
 * document, NOT pixels (see ``substrate.contracts.reading_surface.Region`` and
 * ``substrate/reading/thread_anchor.py``'s anchor-semantics paragraph). This
 * helper computes those offsets from a DOM ``Range`` against the block element
 * that contains it, so a host's ``resolveProvenance`` can hand the FloatMenu a
 * span the backend can anchor + re-locate after re-pagination/re-extraction.
 *
 * WHY block-relative (rigor #5): a thread must survive re-pagination. Page
 * layout is a VIEW concern — the block's text is stable across paginations, so
 * an offset into the block's text re-locates correctly when the same block is
 * re-laid-out on a different page. A whole-document or pixel offset would drift
 * on every reflow.
 *
 * BEST-EFFORT: when the offsets cannot be resolved (the selection spans block
 * boundaries, or ``textContent`` is unavailable) this returns ``null`` for both
 * ends — the thread then anchors to the WHOLE block (char range omitted), which
 * is the honest degradation, never a fabricated offset.
 */

export interface BlockCharRange {
  charStart: number | null;
  charEnd: number | null;
}

const EMPTY: BlockCharRange = { charStart: null, charEnd: null };

/**
 * Char offsets of ``range`` within ``blockEl``'s text content. The block is the
 * element whose text the offsets are measured against (a paragraph / chunk
 * container). Returns whole-block (both null) when the range escapes the block
 * or cannot be measured.
 */
export function charRangeInBlock(range: Range, blockEl: HTMLElement | null): BlockCharRange {
  if (!blockEl) return EMPTY;
  // The selection must live inside the block, or a block-relative offset is
  // meaningless — degrade to whole-block.
  if (!blockEl.contains(range.startContainer) || !blockEl.contains(range.endContainer)) {
    return EMPTY;
  }
  try {
    // char_start = length of the text BEFORE the selection start, within block.
    const pre = range.cloneRange();
    pre.selectNodeContents(blockEl);
    pre.setEnd(range.startContainer, range.startOffset);
    const charStart = pre.toString().length;
    const charEnd = charStart + range.toString().length;
    if (charEnd < charStart) return EMPTY; // defensive — never a reversed range
    return { charStart, charEnd };
  } catch {
    return EMPTY; // any DOM weirdness → honest whole-block anchor
  }
}

/**
 * Find the nearest enclosing block element for ``range`` within ``scope``,
 * preferring an element tagged with a chunk marker (``data-akb-chunk-id``) so
 * the offsets are measured against the SAME block the chunk id names. Falls back
 * to the common-ancestor element, then the scope itself.
 */
export function blockElementFor(range: Range, scope: HTMLElement | null): HTMLElement | null {
  if (!scope) return null;
  let node: Node | null = range.commonAncestorContainer;
  if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
  let el = node as HTMLElement | null;
  // Walk up to a chunk-tagged block if one encloses the selection (the offsets
  // then align with the chunk id the host resolves).
  while (el && el !== scope) {
    if (el.hasAttribute("data-akb-chunk-id")) return el;
    el = el.parentElement;
  }
  // No chunk marker — measure against the common-ancestor element (or scope).
  const anc = range.commonAncestorContainer;
  return (anc.nodeType === Node.TEXT_NODE ? anc.parentElement : (anc as HTMLElement)) ?? scope;
}

/** Convenience: resolve the block-relative char range for a selection ``range``
 * within ``scope``, picking the block element automatically. */
export function resolveCharRange(range: Range, scope: HTMLElement | null): BlockCharRange {
  return charRangeInBlock(range, blockElementFor(range, scope));
}
