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
  /** Invalidate a mounted list when authenticated owner or context changes. */
  scopeKey?: string;
}): UseInvestigationListState {
  const limit = opts?.limit ?? 50;
  const pollMs = opts?.pollIntervalMs ?? 30_000;
  const scopeKey = opts?.scopeKey ?? "";
  const [result, setResult] = useState<{
    scopeKey: string;
    investigations: InvestigationSummary[];
    loading: boolean;
    error: string | null;
  }>({ scopeKey, investigations: [], loading: true, error: null });
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setResult((previous) => ({
      scopeKey,
      investigations: previous.scopeKey === scopeKey ? previous.investigations : [],
      loading: true,
      error: null,
    }));
    void (async () => {
      try {
        const resp = await listInvestigations({ limit });
        if (!cancelled) {
          setResult({ scopeKey, investigations: resp.investigations, loading: false, error: null });
        }
      } catch (e) {
        if (!cancelled) setResult((previous) => ({
          scopeKey,
          investigations: previous.scopeKey === scopeKey ? previous.investigations : [],
          loading: false,
          error: e instanceof Error ? e.message : String(e),
        }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tick, limit, scopeKey]);

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

  return {
    investigations: result.scopeKey === scopeKey ? result.investigations : [],
    loading: result.scopeKey !== scopeKey || result.loading,
    error: result.scopeKey === scopeKey ? result.error : null,
    refetch,
  };
}
