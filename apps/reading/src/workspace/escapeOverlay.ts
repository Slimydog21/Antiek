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
 * window) are not overlays and do not opt in.
 */
export const ESC_OVERLAY_PROPS = { "data-esc-overlay": "" } as const;

const SELECTOR = '[data-esc-overlay], [aria-modal="true"]';

/** Is a transient overlay open on screen (not inside a hidden pane or a
 *  closed <details>)? */
export function escOverlayOpen(root: ParentNode = document): boolean {
  for (const el of root.querySelectorAll<HTMLElement>(SELECTOR)) {
    if (el.closest("[hidden]")) continue;
    const details = el.parentElement?.closest("details");
    if (details && !details.open) continue;
    if (el.getAttribute("aria-hidden") === "true") continue;
    return true;
  }
  return false;
}
