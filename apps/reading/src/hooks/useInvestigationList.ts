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
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [loadedScope, setLoadedScope] = useState(scopeKey);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const resp = await listInvestigations({ limit });
        if (!cancelled) {
          setInvestigations(resp.investigations);
          setLoadedScope(scopeKey);
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

  return { investigations: loadedScope === scopeKey ? investigations : [], loading: loadedScope !== scopeKey || loading, error: loadedScope === scopeKey ? error : null, refetch };
}
