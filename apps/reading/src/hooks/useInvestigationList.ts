import { useCallback, useEffect, useState } from "react";

import { listInvestigations } from "../lib/api";
import type { InvestigationSummary } from "../lib/api";

interface UseInvestigationListState {
  investigations: InvestigationSummary[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Fetches /investigations on mount + polls every 30s while the tab
 * is visible. Pauses polling when document hidden so backgrounded
 * tabs don't ping the substrate uselessly.
 */
export function useInvestigationList(opts?: {
  limit?: number;
  pollIntervalMs?: number;
}): UseInvestigationListState {
  const limit = opts?.limit ?? 50;
  const pollMs = opts?.pollIntervalMs ?? 30_000;
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const resp = await listInvestigations({ limit });
        if (!cancelled) {
          setInvestigations(resp.investigations);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tick, limit]);

  // Polling — only when visible.
  useEffect(() => {
    if (pollMs <= 0) return;
    const onTick = () => {
      if (document.visibilityState === "visible") refetch();
    };
    const id = window.setInterval(onTick, pollMs);
    const onVis = () => {
      if (document.visibilityState === "visible") refetch();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [pollMs, refetch]);

  return { investigations, loading, error, refetch };
}
