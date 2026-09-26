/**
 * useReadingState — the reading-position hook backed by the reading-state
 * bus (reading-global SPR-01). A drop-in for usePosition (the BookReader
 * wiring change is exactly this ONE hook substitution):
 *
 *   - ONE client-side store (a small zustand slice keyed by documentId) is
 *     the same-page authority: every mount of the same document reads the
 *     same entry, so two mounts on one screen show the same page because
 *     they read the same store — never because they signal each other.
 *   - The SERVER row is the cross-device authority: load-on-mount and
 *     refetch on window focus adopt it unconditionally (substrate-wins, the
 *     useInvestigationTree.ts:40-46 merge rule); page turns write through,
 *     debounced, with optimistic concurrency — a 409 re-reads and the
 *     server value wins (never a silent clobber).
 *   - usePosition is the FALLBACK LAYER, composed below: its sessionStorage
 *     carries the position when the bus is unreachable (reading never
 *     blocks on the bus — honest degradation), and its clamp-on-shrink
 *     (usePosition.ts:39-45) is preserved: every adoption and every read
 *     clamps against the live page count.
 */
import { useCallback, useEffect } from "react";
import { create } from "zustand";

import { ApiError } from "../lib/api";
import { getReadingState, putReadingState } from "../api/readingState";
import { usePosition } from "../modes/Reading/usePosition";

export const READING_STATE_DEBOUNCE_MS = 400;

interface ReadingStateEntry {
  pageIndex: number;
  /** The revision to send on the next PUT (0 = no server row known yet). */
  revision: number;
  /** The last server-known anchor ref, echoed on PUT so a position write
   *  never clobbers the engagement ref. */
  anchorRef: string | null;
  loaded: boolean;
  reachable: boolean;
}

interface ReadingStateBus {
  byDocument: Record<string, ReadingStateEntry>;
  /** Register a document (first mount seeds the entry from the
   *  sessionStorage fallback; later mounts never re-seed). */
  ensure: (documentId: string, seedPageIndex: number) => void;
  /** Read the server row; the server value WINS when reachable. */
  load: (documentId: string) => Promise<void>;
  /** A page turn: the shared entry updates immediately (every mount sees
   *  it) and a debounced write-through PUT follows. */
  turn: (documentId: string, pageIndex: number) => void;
  reset: () => void;
}

const debounceTimers = new Map<string, ReturnType<typeof setTimeout>>();
const inflightLoads = new Set<string>();

export const useReadingStateBus = create<ReadingStateBus>()((set, get) => ({
  byDocument: {},

  ensure: (documentId, seedPageIndex) => {
    if (get().byDocument[documentId]) return;
    set((s) => ({
      byDocument: {
        ...s.byDocument,
        [documentId]: {
          pageIndex: seedPageIndex,
          revision: 0,
          anchorRef: null,
          loaded: false,
          reachable: true,
        },
      },
    }));
  },

  load: async (documentId) => {
    if (inflightLoads.has(documentId)) return;
    inflightLoads.add(documentId);
    try {
      const row = await getReadingState(documentId);
      set((s) => {
        const cur = s.byDocument[documentId] ?? {
          pageIndex: 0,
          revision: 0,
          anchorRef: null,
          loaded: false,
          reachable: true,
        };
        return {
          byDocument: {
            ...s.byDocument,
            [documentId]: row
              ? {
                  ...cur,
                  pageIndex: row.page_index,
                  revision: row.revision,
                  anchorRef: row.anchor_ref,
                  loaded: true,
                  reachable: true,
                }
              : { ...cur, loaded: true, reachable: true },
          },
        };
      });
    } catch {
      // The bus is unreachable — honest degradation: the entry keeps its
      // local (sessionStorage-seeded) value; reading never blocks.
      set((s) => {
        const cur = s.byDocument[documentId];
        if (!cur) return s;
        return {
          byDocument: {
            ...s.byDocument,
            [documentId]: { ...cur, loaded: true, reachable: false },
          },
        };
      });
    } finally {
      inflightLoads.delete(documentId);
    }
  },

  turn: (documentId, pageIndex) => {
    set((s) => {
      const cur = s.byDocument[documentId] ?? {
        pageIndex: 0,
        revision: 0,
        anchorRef: null,
        loaded: false,
        reachable: true,
      };
      return {
        byDocument: {
          ...s.byDocument,
          [documentId]: { ...cur, pageIndex },
        },
      };
    });
    const pending = debounceTimers.get(documentId);
    if (pending) clearTimeout(pending);
    debounceTimers.set(
      documentId,
      setTimeout(() => {
        debounceTimers.delete(documentId);
        void flushPut(documentId);
      }, READING_STATE_DEBOUNCE_MS),
    );
  },

  reset: () => {
    for (const t of debounceTimers.values()) clearTimeout(t);
    debounceTimers.clear();
    inflightLoads.clear();
    set({ byDocument: {} });
  },
}));

/** The debounced write-through. A stale revision converges substrate-wins;
 *  an unreachable bus marks the entry and leaves the local value in charge
 *  (the next load/focus retries). */
async function flushPut(documentId: string): Promise<void> {
  const entry = useReadingStateBus.getState().byDocument[documentId];
  if (!entry) return;
  try {
    const resp = await putReadingState(documentId, {
      page_index: entry.pageIndex,
      anchor_ref: entry.anchorRef,
      prefs: {},
      revision: entry.revision,
    });
    useReadingStateBus.setState((s) => {
      const cur = s.byDocument[documentId];
      if (!cur) return s;
      return {
        byDocument: {
          ...s.byDocument,
          [documentId]: {
            ...cur,
            revision: resp.revision,
            anchorRef: resp.anchor_ref,
            reachable: true,
          },
        },
      };
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      // Another writer moved first — re-read; the server value wins.
      await useReadingStateBus.getState().load(documentId);
      return;
    }
    useReadingStateBus.setState((s) => {
      const cur = s.byDocument[documentId];
      if (!cur) return s;
      return {
        byDocument: {
          ...s.byDocument,
          [documentId]: { ...cur, reachable: false },
        },
      };
    });
  }
}

/** Test seam: clear the slice AND any pending debounced writes. */
export function resetReadingStateBus(): void {
  useReadingStateBus.getState().reset();
}

export function useReadingState(
  documentId: string | null,
  pageCount: number,
): { pageIndex: number; setPageIndex: (i: number) => void } {
  // usePosition is the fallback layer: sessionStorage + clamp-on-shrink.
  const {
    pageIndex: fallbackPage,
    setPageIndex: setFallbackPage,
  } = usePosition(documentId, pageCount);

  const entry = useReadingStateBus((s) =>
    documentId ? s.byDocument[documentId] : undefined,
  );
  const ensure = useReadingStateBus((s) => s.ensure);
  const load = useReadingStateBus((s) => s.load);
  const turn = useReadingStateBus((s) => s.turn);

  // Register the document (seeded from the fallback layer), load the server
  // row on mount, and refetch on window focus (the cross-device contract:
  // converge on load/focus, never push).
  useEffect(() => {
    if (!documentId) return;
    ensure(documentId, fallbackPage);
    void load(documentId);
    const onFocus = () => void load(documentId);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
    // fallbackPage is only the seed for a first registration; re-seeding on
    // every turn would fight the store. ensure() no-ops once registered.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, ensure, load]);

  // Substrate-wins (and same-screen convergence): when the store's position
  // diverges from this mount's local layer, adopt it — the fallback layer
  // clamps against the live page count and persists to sessionStorage.
  const storePage = entry?.pageIndex;
  useEffect(() => {
    if (storePage !== undefined && storePage !== fallbackPage) {
      setFallbackPage(storePage);
    }
  }, [storePage, fallbackPage, setFallbackPage]);

  const setPageIndex = useCallback(
    (i: number) => {
      const clamped =
        pageCount > 0 ? Math.max(0, Math.min(i, pageCount - 1)) : Math.max(0, i);
      setFallbackPage(clamped);
      if (documentId) turn(documentId, clamped);
    },
    [documentId, pageCount, setFallbackPage, turn],
  );

  // The clamp rule on READ, too: a stored position past a shortened book
  // snaps to the last page (never an out-of-range render).
  const pageIndex =
    storePage !== undefined
      ? pageCount > 0
        ? Math.max(0, Math.min(storePage, pageCount - 1))
        : Math.max(0, storePage)
      : fallbackPage;

  return { pageIndex, setPageIndex };
}
