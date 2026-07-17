import { createContext, useContext } from "react";

/**
 * windowHostContext — the window-adaptation contract seam (SPR-09 M4).
 *
 * A product page rendered as a full-page route knows nothing about windows.
 * When the SAME page is hosted inside a WorkspaceWindow, it needs exactly two
 * (and ONLY two) adaptations, per the bounded window-adaptation contract:
 *
 *   (a) drop its opaque full-bleed background so the glass body — and the
 *       mountainscape behind it — shows through, and
 *   (b) fill its container (h-full) instead of forcing the full viewport
 *       height (h-screen), which would overflow the window frame.
 *
 * Rather than fork each page or edit it unconditionally (which would subtly
 * change the full-page route), the page reads this context. It defaults to
 * `false`, so a page rendered at its normal route is byte-for-byte unchanged
 * at runtime; only a page mounted under <WindowHostProvider> adapts.
 *
 * This is the WHOLE contract. A page that needs MORE than (a)+(b) to float is
 * out-of-contract and must be reported, not redesigned (SPR-09 rigor #1).
 */
export const WindowHostContext = createContext<boolean>(false);
const WindowInstanceContext = createContext<string | null>(null);

/** True when the calling component tree is rendered inside a WorkspaceWindow. */
export function useInWindow(): boolean {
  return useContext(WindowHostContext);
}

/** Exact presentation host id, or null for routes and legacy panels. */
export function useWindowInstanceId(): string | null {
  return useContext(WindowInstanceContext);
}

export const WindowHostProvider = WindowHostContext.Provider;
export const WindowInstanceProvider = WindowInstanceContext.Provider;
