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

export const READ_POSITION_EVENT = "antiek:read-position";

export function readPositionKey(documentId: string): string {
  return `antiek.read.pos.${documentId}`;
}

export function readStoredPosition(documentId: string): number {
  try {
    const raw = window.sessionStorage.getItem(readPositionKey(documentId));
    if (raw === null || !/^\d+$/.test(raw)) return 0;
    const n = Number(raw);
    return Number.isSafeInteger(n) ? n : 0;
  } catch {
    return 0;
  }
}

function publishPosition(documentId: string, pageIndex: number): void {
  try {
    window.sessionStorage.setItem(readPositionKey(documentId), String(pageIndex));
  } catch {
    /* sessionStorage unavailable (private mode) — position is best-effort. */
  }
  window.dispatchEvent(
    new CustomEvent(READ_POSITION_EVENT, {
      detail: { documentId, pageIndex },
    }),
  );
}

export function usePosition(
  documentId: string | null,
  pageCount: number,
): { pageIndex: number; setPageIndex: (i: number) => void } {
  const [pageIndex, setPageIndexState] = useState<number>(() =>
    documentId ? readStoredPosition(documentId) : 0,
  );

  // When the document changes, restore that document's saved position.
  useEffect(() => {
    if (documentId) setPageIndexState(readStoredPosition(documentId));
  }, [documentId]);

  // Clamp into range whenever the page count resolves (a saved position
  // past the end of a now-shorter book snaps to the last page).
  useEffect(() => {
    if (pageCount > 0) {
      setPageIndexState((p) => Math.max(0, Math.min(p, pageCount - 1)));
    }
  }, [pageCount]);

  useEffect(() => {
    if (documentId) publishPosition(documentId, pageIndex);
  }, [documentId, pageIndex]);

  const setPageIndex = useCallback(
    (i: number) => {
      const clamped = pageCount > 0 ? Math.max(0, Math.min(i, pageCount - 1)) : Math.max(0, i);
      setPageIndexState(clamped);
    },
    [pageCount],
  );

  return { pageIndex, setPageIndex };
}
