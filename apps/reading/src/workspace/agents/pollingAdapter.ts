/**
 * agents/pollingAdapter.ts — SPR-10 M2: the LIST-ONLY polling source.
 * `useInvestigationList` (hooks/useInvestigationList.ts) already pauses
 * while hidden, refetches on visibilitychange and keeps the previous rows
 * on error; none of that is re-implemented. 2 s while any watched run is
 * live, 30 s otherwise, 200 rows. The per-id route is never read: it
 * reports halted runs as in progress and lacks `stopped`
 * (interfaces/research/api/app.py:3379-3393 vs :3550-3554; handoff §6.5).
 * SPR-B's push source replaces this one file by calling `observe` /
 * `setNeedsInput` on the store.
 */
import { useEffect } from "react";

import { useInvestigationList } from "../../hooks/useInvestigationList";
import type { InvestigationSummary } from "../../lib/api";
import { phaseOf, type RawObservation } from "./agentStatus";
import { useAgentStatusStore, type StatusClock } from "./agentStatusStore";
import { DEBOUNCE } from "./debounce";

export const POLL_LIMIT = 200;

/** Live = never observed yet, working, or unknown without a not_found detail. */
export function anyLiveAmong(raw: ReadonlyMap<string, RawObservation>, watched: ReadonlySet<string>): boolean {
  for (const id of watched) {
    const r = raw.get(id);
    if (!r) return true;
    const row = phaseOf(r.status);
    if (row.phase === "working") return true;
    if (row.phase === "unknown" && row.detail === undefined) return true;
  }
  return false;
}

export function usePollingStatusSource(watched: ReadonlySet<string>, clock: StatusClock): void {
  const anyLive = useAgentStatusStore((s) => anyLiveAmong(s.raw, watched));
  const { investigations } = useInvestigationList({
    limit: POLL_LIMIT,
    pollIntervalMs: anyLive ? DEBOUNCE.pollMs : DEBOUNCE.idlePollMs,
  });
  useEffect(() => {
    useAgentStatusStore.getState().observe(investigations, watched, clock.now());
  }, [investigations, watched, clock]);
}

/** The latest list snapshot (confirm re-reads). */
export function latestSnapshot(): readonly InvestigationSummary[] {
  return useAgentStatusStore.getState().snapshot;
}
