import { useCallback, useEffect, useSyncExternalStore } from "react";

import { listInvestigations } from "../lib/api";
import type { InvestigationSummary } from "../lib/api";

/**
 * Shared investigation-list store (herdr transfer P1) — ONE poller for every
 * consumer. Before this, the home route mounted up to four independent
 * `useInvestigationList` instances (MyResearch, InvestigationSidebar,
 * NavRail, SuggestedResearch), each polling /investigations on its own timer.
 * Now the fetch + list live in one module-level store with a single
 * interval, and every hook instance is a subscriber (useSyncExternalStore).
 * `refetch()` from any surface refreshes all.
 *
 * The interface is unchanged: { investigations, loading, error, refetch }.
 * The effective list limit is the MAXIMUM requested by any mounted consumer
 * (a 200-limit log and a 50-limit badge share one fetch of 200 — one extra
 * row for the badge costs nothing; a second fetch costs a round-trip).
 */

interface SharedListState {
  investigations: InvestigationSummary[];
  loading: boolean;
  error: string | null;
  /** Effective limit = max across mounted consumers. */
  maxLimit: number;
  /** Poll cadence of the FASTEST consumer (the log's 30s drives the badge's
   *  60s — a shared store has one clock). */
  pollMs: number;
  /** Bumped by refetch() to force a fresh fetch. */
  tick: number;
}

let shared: SharedListState = {
  investigations: [],
  loading: true,
  error: null,
  maxLimit: 50,
  pollMs: 30_000,
  tick: 0,
};

const listeners = new Set<() => void>();
let mountedCount = 0;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let inFlight: Promise<void> | null = null;

function emit(): void {
  for (const l of listeners) l();
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/** Stable snapshot for useSyncExternalStore (mutated in place + emit). */
function getSnapshot(): SharedListState {
  return shared;
}

async function fetchNow(): Promise<void> {
  if (inFlight) return inFlight;
  inFlight = (async () => {
    try {
      const resp = await listInvestigations({ limit: shared.maxLimit });
      // Immutable replacement — useSyncExternalStore only re-renders when
      // the snapshot REFERENCE changes.
      shared = { ...shared, investigations: resp.investigations, error: null };
    } catch (e) {
      shared = {
        ...shared,
        error: e instanceof Error ? e.message : String(e),
      };
    } finally {
      shared = { ...shared, loading: false };
      inFlight = null;
      emit();
    }
  })();
  return inFlight;
}

function ensurePolling(): void {
  if (pollTimer) return;
  const onTick = () => {
    if (typeof document === "undefined" || document.visibilityState === "visible") {
      void fetchNow();
    }
  };
  void fetchNow();
  pollTimer = setInterval(onTick, shared.pollMs);
}

function stopPolling(): void {
  if (pollTimer && mountedCount === 0) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

interface UseInvestigationListState {
  investigations: InvestigationSummary[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Subscribe to the shared investigation list. Polling runs while ANY
 *  consumer is mounted; pauses when the tab is hidden (unchanged rule). */
export function useInvestigationList(opts?: {
  limit?: number;
  pollIntervalMs?: number;
}): UseInvestigationListState {
  const limit = opts?.limit ?? 50;
  const pollMs = opts?.pollIntervalMs ?? 30_000;

  // Register the consumer's requirements on the shared store.
  useEffect(() => {
    mountedCount += 1;
    const maxLimit = Math.max(limit, shared.maxLimit);
    const minPollMs = Math.min(pollMs, shared.pollMs);
    const changed = maxLimit !== shared.maxLimit || minPollMs !== shared.pollMs;
    shared = { ...shared, maxLimit, pollMs: minPollMs };
    if (changed && pollTimer) {
      // Restart the poller on the new cadence + refetch at the new limit.
      clearInterval(pollTimer);
      pollTimer = null;
    }
    ensurePolling();
    emit();
    return () => {
      mountedCount -= 1;
      if (mountedCount === 0) {
        stopPolling();
        // Fresh mount after a full unmount starts clean (no stale list).
        shared = {
          ...shared,
          investigations: [],
          loading: true,
          error: null,
          maxLimit: 50,
          pollMs: 30_000,
        };
      }
      emit();
    };
  }, [limit, pollMs]);

  const state = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const refetch = useCallback(() => {
    shared = { ...shared, tick: shared.tick + 1 };
    void fetchNow();
  }, []);

  return {
    investigations: state.investigations,
    loading: state.loading,
    error: state.error,
    refetch,
  };
}
