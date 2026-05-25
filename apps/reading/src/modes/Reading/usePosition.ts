import { useCallback, useEffect, useState } from "react";

/**
 * Reading position (Read SPR-03; reused by SPR-08 return-to-reading).
 *
 * Persists the current page index per book to sessionStorage so that
 * spinning a research from a passage (SPR-08) and returning lands the
 * reader on the exact page the reader left. Position is a locator
 * (page index), not a scroll offset — it survives re-layout, font
 * changes, and viewport size, because the page window is content-derived
 * (see `paginate.ts`).
 */

const KEY = (documentId: string) => `antiek.read.pos.${documentId}`;

function readStored(documentId: string): number {
  try {
    const raw = window.sessionStorage.getItem(KEY(documentId));
    const n = raw === null ? 0 : parseInt(raw, 10);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch {
    return 0;
  }
}

export function usePosition(
  documentId: string | null,
  pageCount: number,
): { pageIndex: number; setPageIndex: (i: number) => void } {
  const [pageIndex, setPageIndexState] = useState<number>(() =>
    documentId ? readStored(documentId) : 0,
  );

  // When the document changes, restore that document's saved position.
  useEffect(() => {
    if (documentId) setPageIndexState(readStored(documentId));
  }, [documentId]);

  // Clamp into range whenever the page count resolves (a saved position
  // past the end of a now-shorter book snaps to the last page).
  useEffect(() => {
    if (pageCount > 0) {
      setPageIndexState((p) => Math.max(0, Math.min(p, pageCount - 1)));
    }
  }, [pageCount]);

  const setPageIndex = useCallback(
    (i: number) => {
      const clamped = pageCount > 0 ? Math.max(0, Math.min(i, pageCount - 1)) : Math.max(0, i);
      setPageIndexState(clamped);
      if (documentId) {
        try {
          window.sessionStorage.setItem(KEY(documentId), String(clamped));
        } catch {
          /* sessionStorage unavailable (private mode) — position is
             best-effort; reading still works, it just won't persist. */
        }
      }
    },
    [documentId, pageCount],
  );

  return { pageIndex, setPageIndex };
}
