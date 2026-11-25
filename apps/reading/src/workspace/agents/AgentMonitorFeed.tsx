/**
 * agents/AgentMonitorFeed.tsx — SPR-10 (lazy): the monitor's one mount.
 * Feeds the context tree (the ONE <PreBackendTreeFeed /> line CONTRACTS.md
 * §3 step 2 names; refcounted, so SPR-04's mount coexists), starts the
 * store with the real clock, runs the list-only polling source over the
 * tree's research runs, installs the status toasts. This is the only file
 * under agents/ that imports the pre-backend adapter.
 *
 * DEV-only seam: `window.__antiekAgentStatus = { setNeedsInput, observe }`
 * for J5's blocked leg (no wire carries needs-input today; handoff §6.1).
 * Never in production builds.
 */
import { useEffect } from "react";

import type { InvestigationSummary } from "../../lib/api";
import { PreBackendTreeFeed } from "../contracts/adapters/preBackend";
import { realClock, useAgentStatusStore, useWatchedIds } from "./agentStatusStore";
import { usePollingStatusSource } from "./pollingAdapter";
import { installStatusToasts } from "./statusToasts";

declare global {
  interface Window {
    __antiekAgentStatus?: {
      setNeedsInput: (runId: string, flag: boolean) => void;
      observe: (summaries: readonly InvestigationSummary[], watched: readonly string[]) => void;
    };
  }
}

export default function AgentMonitorFeed({ feedTree = true }: { feedTree?: boolean }) {
  useEffect(() => {
    const store = useAgentStatusStore.getState();
    store.start(realClock);
    const uninstall = installStatusToasts();
    return () => {
      uninstall();
      store.stop();
    };
  }, []);

  const watched = useWatchedIds();
  usePollingStatusSource(watched, realClock);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    window.__antiekAgentStatus = {
      setNeedsInput: (runId, flag) => useAgentStatusStore.getState().setNeedsInput(runId, flag),
      observe: (summaries, ids) => useAgentStatusStore.getState().observe(summaries, new Set(ids), realClock.now()),
    };
    return () => {
      delete window.__antiekAgentStatus;
    };
  }, []);

  return feedTree ? <PreBackendTreeFeed investigationLimit={50} /> : null;
}
