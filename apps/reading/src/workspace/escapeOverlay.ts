/**
 * escapeOverlay.ts — "one Esc reaches exactly one handler" (lane A B2-2).
 *
 * A transient overlay (a dropdown menu, a select's listbox, a modal, the
 * selection FloatMenu, the tab-tree popover, the reader's contents drawer)
 * owns the Esc while it is open: the Esc closes it and nothing else. The
 * fullscreen restore in PanelLayout listens on the document, and listener
 * order between the document and the window is not something an overlay
 * can rely on, so the restore asks the DOM instead: while any overlay is
 * on screen, Esc is not the restore's. The overlay's own close removes it,
 * so the NEXT Esc restores.
 *
 * An overlay opts in with the attribute (spread ESC_OVERLAY_PROPS on its
 * root); an aria-modal dialog is one by definition. Persistent regions that
 * happen to carry a menu/listbox/dialog role (the style rail, a floating
 * window) are not overlays and do not opt in, with one exception: the
 * FOCUSED floating workspace panel owns Esc (its Esc closes it), so it opts
 * in while focused (PanelLayoutPanel, R2-M2).
 */
export const ESC_OVERLAY_PROPS = { "data-esc-overlay": "" } as const;

const listenerOwners = new WeakMap<Document, Set<symbol>>();

/** Declare the actual listener's document until that listener is removed.
 *  Unlike a DOM marker, this also covers a mounted menu that renders null. */
export function registerEscapeListenerOwnership(ownerDocument: Document): () => void {
  const owners = listenerOwners.get(ownerDocument) ?? new Set<symbol>();
  const token = Symbol();
  owners.add(token);
  listenerOwners.set(ownerDocument, owners);
  return () => {
    if (!owners.delete(token)) return;
    if (owners.size === 0) listenerOwners.delete(ownerDocument);
  };
}

function isDocument(root: ParentNode): root is Document {
  return root.nodeType === 9;
}

const SELECTOR = '[data-esc-overlay], [aria-modal="true"]';

/** Is an overlay visible or an Escape listener mounted in this document?
 *  Element/fragment queries keep the DOM visibility and except rules below. */
export function escOverlayOpen(root: ParentNode = document, except: Element | null = null): boolean {
  if (isDocument(root) && listenerOwners.get(root)?.size) return true;
  for (const el of root.querySelectorAll<HTMLElement>(SELECTOR)) {
    if (el === except || el.closest("[hidden]")) continue;
    const details = el.parentElement?.closest("details");
    if (details && !details.open) continue;
    if (el.getAttribute("aria-hidden") === "true") continue;
    return true;
  }
  return false;
}


/** Portalled dialogs share a stacking level; the last visible dialog owns Escape. */
export function topModal(root: ParentNode = document): HTMLElement | null {
  const dialogs = Array.from(root.querySelectorAll<HTMLElement>('[aria-modal="true"]'));
  return dialogs.filter((el) => {
    if (el.closest('[hidden], [aria-hidden="true"]')) return false;
    const details = el.parentElement?.closest("details");
    return !details || details.open;
  }).at(-1) ?? null;
}

/** The topmost visible overlay of any kind (data-esc-overlay or aria-modal),
 *  same DOM-order convention as topModal: the last visible match owns Escape.
 *  Universal popover rule (wave repair, design-lead call 2026-10-08): an Esc
 *  with body/global focus closes the top floating card, so a card must be able
 *  to ask whether it IS that top overlay. */
export function topEscOverlay(root: ParentNode = document): HTMLElement | null {
  const overlays = Array.from(root.querySelectorAll<HTMLElement>(SELECTOR));
  return overlays.filter((el) => {
    if (el.closest('[hidden], [aria-hidden="true"]')) return false;
    const details = el.parentElement?.closest("details");
    return !details || details.open;
  }).at(-1) ?? null;
}
