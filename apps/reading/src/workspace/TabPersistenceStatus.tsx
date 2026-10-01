import type { Mothership } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";

export type TabSaveStatus = "session" | "paused" | "unavailable" | "loading" | "unsaved" | "pending" | "saved";
type TabState = ReturnType<typeof useTabTrees.getState>;

function statusForTabs(state: TabState, mothership: Mothership): TabSaveStatus {
  if (state.tabsPersistence === "session") return "session";
  if (!state.dispatchAllowed) return "paused";
  if (state.loadError[mothership]) return "unavailable";
  if (!state.loaded[mothership]) return "loading";
  if (state.persistenceIssues[mothership]) return "unsaved";
  if (state.saving[mothership] || state.pendingOps[mothership].length || state.heldClose?.mothership === mothership) return "pending";
  return "saved";
}

const MESSAGES = {
  session: "Tabs last for this session.",
  paused: "Tab saving is paused.",
  unavailable: "Saved tabs are unavailable.",
  loading: "Loading saved tabs.",
  unsaved: "Tab changes aren't saved yet.",
  pending: "Tab changes pending.",
  saved: "Tabs saved.",
} satisfies Record<TabSaveStatus, string>;

export function TabPersistenceStatusView({ status, saving = false, onRetryLoad, onRetrySave }: {
  status: TabSaveStatus;
  saving?: boolean;
  onRetryLoad: () => void;
  onRetrySave: () => void;
}) {
  const retry = status === "unavailable" ? { label: "Retry loading tabs", run: onRetryLoad }
    : status === "unsaved" ? { label: "Retry saving tabs", run: onRetrySave } : null;
  return (
    <div className="flex items-center gap-2 px-3 py-1 text-xs text-shadow-2 dark:text-shadow-1 bg-ice-1 dark:bg-charcoal-1">
      <span role="status">{MESSAGES[status]}</span>
      {retry && <button type="button" disabled={saving}
        className="underline underline-offset-2 focus-visible:outline focus-visible:outline-2"
        onClick={retry.run}>{retry.label}</button>}
    </div>
  );
}

export function TabPersistenceStatus({ mothership }: { mothership: Mothership }) {
  const status = useTabTrees((state) => statusForTabs(state, mothership));
  const saving = useTabTrees((state) => state.saving[mothership]);
  return <TabPersistenceStatusView status={status} saving={saving}
    onRetryLoad={() => { void useTabTrees.getState().retryLoad(mothership); }}
    onRetrySave={() => useTabTrees.getState().retrySave(mothership)} />;
}
