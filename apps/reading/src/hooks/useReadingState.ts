/**
 * useReadingState — the reading-position hook backed by the reading-state
 * bus (reading-global SPR-01).
 *
 *   - One client-side store (a small zustand slice keyed by documentId) is
 *     the same-page authority: every mount of the same document reads the
 *     same entry, so two mounts on one screen show the same page because
 *     they read the same store — never because they signal each other.
 *   - The server row wins on mount, focus and a genuine 409 when no local
 *     turn remains unsettled. A pending turn keeps its page while GET
 *     supplies the current revision. Writes run serially so a later turn
 *     uses the preceding write's revision.
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
import { notifyReadingPositionOwner, readingPositionOwner, setReadingPositionOwner, usePosition, usePositionOwner } from "../modes/Reading/usePosition";

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
  turnVersion: number;
  settledVersion: number;
}

interface ReadingStateBus {
  byDocument: Record<string, ReadingStateEntry>;
  /** Register a document (first mount seeds the entry from the
   *  sessionStorage fallback; later mounts never re-seed). */
  ensure: (documentId: string, seedPageIndex: number) => void;
  /** Read the server row without erasing an unsettled local turn. */
  load: (documentId: string) => Promise<void>;
  /** A page turn: the shared entry updates immediately (every mount sees
   *  it) and a debounced write-through PUT follows. */
  turn: (documentId: string, pageIndex: number) => void;
  reset: () => void;
}

const debounceTimers = new Map<string, ReturnType<typeof setTimeout>>();
const inflightLoads = new Map<string, Promise<void>>();
const activeWrites = new Set<string>();
let generation = 0;
let owner: string | null = null;

function current(requestGeneration: number): boolean {
  return requestGeneration === generation;
}

function flushIfReady(documentId: string): void {
  const entry = useReadingStateBus.getState().byDocument[documentId];
  if (
    entry && entry.loaded && entry.turnVersion > entry.settledVersion &&
    !debounceTimers.has(documentId) && !activeWrites.has(documentId)
  ) void flushPut(documentId);
}

function seedEntry(pageIndex: number): ReadingStateEntry {
  return {
    pageIndex, revision: 0, anchorRef: null, loaded: false, reachable: true,
    turnVersion: 0, settledVersion: 0,
  };
}

export const useReadingStateBus = create<ReadingStateBus>()((set, get) => ({
  byDocument: {},

  ensure: (documentId, seedPageIndex) => {
    if (get().byDocument[documentId]) return;
    set((s) => ({
      byDocument: {
        ...s.byDocument,
        [documentId]: seedEntry(seedPageIndex),
      },
    }));
  },

  load: async (documentId) => {
    const existing = inflightLoads.get(documentId);
    if (existing) return existing;
    const requestGeneration = generation;
    const startSettledVersion = get().byDocument[documentId]?.settledVersion ?? 0;
    let retryAfterThisLoad = false;
    const work = (async () => {
    try {
      const row = await getReadingState(documentId);
      if (!current(requestGeneration)) return;
      set((s) => {
        const cur = s.byDocument[documentId];
        if (!cur) return s;
        if (cur.settledVersion > startSettledVersion) return s;
        const pendingTurn = cur.turnVersion > cur.settledVersion;
        return {
          byDocument: {
            ...s.byDocument,
            [documentId]: {
              ...cur,
              pageIndex: row && !pendingTurn ? row.page_index : cur.pageIndex,
              revision: row?.revision ?? 0,
              anchorRef: row?.anchor_ref ?? null,
              loaded: true,
              reachable: true,
            },
          },
        };
      });
    } catch {
      if (!current(requestGeneration)) return;
      retryAfterThisLoad = true;
      // The bus is unreachable — honest degradation: the entry keeps its
      // local (sessionStorage-seeded) value; reading never blocks.
      set((s) => {
        const cur = s.byDocument[documentId];
        if (!cur) return s;
        if (cur.settledVersion > startSettledVersion) return s;
        return {
          byDocument: {
            ...s.byDocument,
            [documentId]: { ...cur, loaded: true, reachable: false },
          },
        };
      });
    } finally {
      if (current(requestGeneration)) {
        inflightLoads.delete(documentId);
        // A failed GET is not proof that writes can succeed. Retry only after
        // a successful read restores evidence that the bus is reachable.
        if (!retryAfterThisLoad) flushIfReady(documentId);
      }
    }
    })();
    inflightLoads.set(documentId, work);
    return work;
  },

  turn: (documentId, pageIndex) => {
    set((s) => {
      const cur = s.byDocument[documentId] ?? seedEntry(0);
      return {
        byDocument: {
          ...s.byDocument,
          [documentId]: { ...cur, pageIndex, turnVersion: cur.turnVersion + 1 },
        },
      };
    });
    const pending = debounceTimers.get(documentId);
    if (pending) clearTimeout(pending);
    debounceTimers.set(
      documentId,
      setTimeout(() => {
        debounceTimers.delete(documentId);
        flushIfReady(documentId);
      }, READING_STATE_DEBOUNCE_MS),
    );
  },

  reset: () => {
    generation += 1;
    for (const t of debounceTimers.values()) clearTimeout(t);
    debounceTimers.clear();
    inflightLoads.clear();
    activeWrites.clear();
    set({ byDocument: {} });
  },
}));

/** A single in-flight write per document. A 409 refetches the server row;
 *  a later local turn remains pending and retries with the new revision. */
async function flushPut(documentId: string): Promise<void> {
  const requestGeneration = generation;
  const entry = useReadingStateBus.getState().byDocument[documentId];
  if (!entry || activeWrites.has(documentId)) return;
  activeWrites.add(documentId);
  let retryFromThisFailure = false;
  try {
    const resp = await putReadingState(documentId, {
      page_index: entry.pageIndex,
      anchor_ref: entry.anchorRef,
      prefs: {},
      revision: entry.revision,
    });
    if (!current(requestGeneration)) return;
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
            settledVersion: entry.turnVersion,
            reachable: true,
          },
        },
      };
    });
  } catch (e) {
    if (!current(requestGeneration)) return;
    if (e instanceof ApiError && e.status === 409) {
      // A later local turn survives the refetch. Otherwise the competing
      // device's row wins.
      useReadingStateBus.setState((s) => {
        const cur = s.byDocument[documentId];
        if (!cur) return s;
        return {
          byDocument: {
            ...s.byDocument,
            [documentId]: { ...cur, settledVersion: entry.turnVersion },
          },
        };
      });
      const joinedOlderLoad = inflightLoads.has(documentId);
      await useReadingStateBus.getState().load(documentId);
      if (joinedOlderLoad && current(requestGeneration)) {
        await useReadingStateBus.getState().load(documentId);
      }
      return;
    }
    retryFromThisFailure = true;
    useReadingStateBus.setState((s) => {
      const cur = s.byDocument[documentId];
      if (!cur) return s;
      return {
        byDocument: {
          ...s.byDocument,
        // The server did not accept the turn. Keep it pending; a later
        // successful read may retry it without a failure-driven loop.
          [documentId]: { ...cur, settledVersion: cur.settledVersion, reachable: false },
        },
      };
    });
  } finally {
    if (current(requestGeneration) && !retryFromThisFailure) {
      activeWrites.delete(documentId);
      flushIfReady(documentId);
    } else if (current(requestGeneration)) {
      activeWrites.delete(documentId);
    }
  }
}

export function setReadingStateOwner(nextOwner: string | null): void {
  if (owner === nextOwner) return;
  owner = nextOwner;
  setReadingPositionOwner(nextOwner, false);
  useReadingStateBus.getState().reset();
  notifyReadingPositionOwner();
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
  const positionOwner = usePositionOwner();
  const ownerGeneration = generation;

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
    if (!documentId || ownerGeneration !== generation) return;
    ensure(documentId, fallbackPage);
    void load(documentId);
    const onFocus = () => {
      if (ownerGeneration === generation) void load(documentId);
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
    // fallbackPage is only the seed for a first registration; re-seeding on
    // every turn would fight the store. ensure() no-ops once registered.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, ownerGeneration, positionOwner, ensure, load]);

  // Store-to-fallback synchronization: when the store's position
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
      if (positionOwner !== readingPositionOwner() || ownerGeneration !== generation) return;
      const clamped =
        pageCount > 0 ? Math.max(0, Math.min(i, pageCount - 1)) : Math.max(0, i);
      setFallbackPage(clamped);
      if (documentId) turn(documentId, clamped);
    },
    [documentId, ownerGeneration, pageCount, positionOwner, setFallbackPage, turn],
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
