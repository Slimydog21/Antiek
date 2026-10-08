import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useWorkspaceOwner, workspaceOwnerAdmission, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";

/**
 * Reading position (Read SPR-03; reused by SPR-08 return-to-reading).
 *
 * Persists the current page index per owner and book to sessionStorage so that
 * spinning a research from a passage (SPR-08) and returning lands the
 * reader on the exact page the reader left. Position is a locator
 * (page index), not a scroll offset — it survives re-layout, font
 * changes, and viewport size, because the page window is content-derived
 * (see `paginate.ts`).
 */

let owner: string | null = null;
let ownerEpoch = 0;
const ownerListeners = new Set<() => void>();

export function setReadingPositionOwner(nextOwner: string | null, notify = true): void {
  if (owner === nextOwner) return;
  owner = nextOwner;
  ownerEpoch += 1;
  if (notify) notifyReadingPositionOwner();
}

export function notifyReadingPositionOwner(): void {
  for (const listener of ownerListeners) listener();
}

function subscribeOwner(listener: () => void): () => void {
  ownerListeners.add(listener);
  return () => ownerListeners.delete(listener);
}

function currentOwner(): string | null {
  return owner;
}

export function readingPositionOwner(): string | null {
  return owner;
}

export function readingPositionOwnerEpoch(): number {
  return ownerEpoch;
}

export function usePositionOwnerEpoch(): number {
  return useSyncExternalStore(subscribeOwner, readingPositionOwnerEpoch);
}

export function usePositionOwner(): string | null {
  return useSyncExternalStore(subscribeOwner, currentOwner);
}

export function positionStorageKey(documentId: string): string {
  return `antiek.read.pos.${encodeURIComponent(owner ?? "anonymous")}.${encodeURIComponent(documentId)}`;
}

function readStored(documentId: string): number {
  try {
    const raw = window.sessionStorage.getItem(positionStorageKey(documentId));
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
  const epoch = usePositionOwnerEpoch();
  const account = useWorkspaceOwner();
  const storageKey = documentId ? positionStorageKey(documentId) : null;
  const resource = useMemo(() => ({ storageKey, epoch, account, active: false }), [storageKey, epoch, account]);
  const resourceRef = useRef(resource);
  useLayoutEffect(() => {
    resourceRef.current = resource;
    resource.active = true;
    return () => { resource.active = false; };
  }, [resource]);
  const [position, setPosition] = useState(() => ({
    key: storageKey,
    pageIndex: documentId ? readStored(documentId) : 0,
  }));
  const pageIndex = position.key === storageKey
    ? position.pageIndex
    : documentId ? readStored(documentId) : 0;

  // When the document changes, restore that document's saved position.
  useEffect(() => {
    setPosition({ key: storageKey, pageIndex: documentId ? readStored(documentId) : 0 });
  }, [documentId, storageKey]);

  // Clamp into range whenever the page count resolves (a saved position
  // past the end of a now-shorter book snaps to the last page).
  useEffect(() => {
    if (pageCount > 0) {
      setPosition((p) => ({
        key: storageKey,
        pageIndex: Math.max(0, Math.min(p.key === storageKey ? p.pageIndex : documentId ? readStored(documentId) : 0, pageCount - 1)),
      }));
    }
  }, [documentId, pageCount, storageKey]);

  const pageCountRef = useRef(pageCount);
  useLayoutEffect(() => { pageCountRef.current = pageCount; }, [pageCount]);

  const setPageIndex = useCallback(
    (i: number) => {
      const admission = workspaceOwnerAdmission();
      if (!resource.active || resourceRef.current !== resource || resource.epoch !== readingPositionOwnerEpoch()
        || resource.account !== workspaceOwnerSession()
        || admission.state === "retiring" || admission.state === "failed") return;
      if (documentId && storageKey !== positionStorageKey(documentId)) return;
      const count = pageCountRef.current;
      const clamped = count > 0 ? Math.max(0, Math.min(i, count - 1)) : Math.max(0, i);
      setPosition({ key: storageKey, pageIndex: clamped });
      if (storageKey) {
        try {
          window.sessionStorage.setItem(storageKey, String(clamped));
        } catch {
          /* sessionStorage unavailable (private mode) — position is
             best-effort; reading still works, it just won't persist. */
        }
      }
    },
    [documentId, storageKey, resource, resourceRef, pageCountRef],
  );

  return { pageIndex, setPageIndex };
}
