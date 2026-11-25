import { Suspense, lazy } from "react";

// ENTRY-SAFE shell: the monitor (the store, the poller, the toast queue and
// the tree feeder) loads lazily, so the entry chunk carries only this.
const AgentMonitorFeed = lazy(() => import("./AgentMonitorFeed"));

export interface AgentMonitorProps {
  /** Mount the pre-backend tree feeder here (CONTRACTS.md §3 step 2's one
   *  line). Refcounted, so another mount coexists; whichever lands second
   *  drops its line. */
  feedTree?: boolean;
}

/**
 * AgentMonitor — SPR-10: mount ONCE in AppShell. Starts the agent status
 * store, polls the investigation list for the runs the tree knows, and
 * installs the status toasts.
 */
export function AgentMonitor(props: AgentMonitorProps) {
  return (
    <Suspense fallback={null}>
      <AgentMonitorFeed {...props} />
    </Suspense>
  );
}

export default AgentMonitor;
