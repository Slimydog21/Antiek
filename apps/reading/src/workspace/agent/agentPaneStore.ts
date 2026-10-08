/**
 * agentPaneStore.ts — the agent pane's session state (SPR-07): the close
 * linger, the recording stub, dismissed context chips, and the open nonce
 * that refocuses the composer on re-activation. Also the two seams the
 * pane shares with the companion: closeAgentPane (the 240 ms inert linger
 * before the companion's own close-with-undo, then focus return) and
 * useSyncProjectFilter (the selection → companionStore.projectFilter wire;
 * the store never reads the selection itself, openers.ts imports it and a
 * back-import would be a cycle). CompanionPane calls the wire: it is
 * mounted whenever the strip is, so the filter can never go stale while a
 * tab is visible (repair 2026-10-07T22:40Z, finding 1; AgentPane calling it
 * unsubscribed with the pane, and the hidden-tab placeholder unmounts it).
 */
import { useEffect, useSyncExternalStore } from "react";
import { toast, UNDO_TTL_MS } from "../../components/lemon/LemonToast";
import { awaitWorkspaceOwnerSession, isWorkspaceOwnerSession, subscribeWorkspaceOwnerAdmission, workspaceOwnerAdmission, workspaceOwnerSession, type WorkspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { create } from "zustand";

import { isConfirmedAgentOwner } from "./turnLifecycle";

import { agentTabDomId } from "../agentTabDomId";
import { tabVisible, useCompanion } from "../companionStore";
import { useSelection } from "../contracts/selection";

/** refs pattern 7: the surface stays, inert, long enough for the close to
 *  read as a close; then the tab goes behind the shared 10 s Undo. */
export const CLOSE_LINGER_MS = 240;

interface AgentPaneState {
  closing: Record<string, true>;
  recording: Record<string, boolean>;
  /** tabId → anchorKey of the dismissed context chip. */
  chipDismissed: Record<string, string>;
  openNonce: Record<string, number>;
  setClosing: (tabId: string, on: boolean) => void;
  setRecording: (tabId: string, on: boolean) => void;
  dismissChip: (tabId: string, anchorKey: string) => void;
  bumpNonce: (tabId: string) => void;
  reset: () => void;
}

export const useAgentPaneStore = create<AgentPaneState>()((set) => ({
  closing: {},
  recording: {},
  chipDismissed: {},
  openNonce: {},
  setClosing: (tabId, on) =>
    set((s) => {
      const { [tabId]: _drop, ...rest } = s.closing;
      return { closing: on ? { ...rest, [tabId]: true } : rest };
    }),
  setRecording: (tabId, on) => set((s) => ({ recording: { ...s.recording, [tabId]: on } })),
  dismissChip: (tabId, anchorKey) => set((s) => ({ chipDismissed: { ...s.chipDismissed, [tabId]: anchorKey } })),
  bumpNonce: (tabId) => set((s) => ({ openNonce: { ...s.openNonce, [tabId]: (s.openNonce[tabId] ?? 0) + 1 } })),
  reset: () => set({ closing: {}, recording: {}, chipDismissed: {}, openNonce: {} }),
}));

/** After the tab is gone: the next visible companion tab's root, else the
 *  left pane. Never left on <body> (fix 5). */
function returnFocusAfterClose(): void {
  const c = useCompanion.getState();
  const active = c.activeTabId ? c.tabs.find((t) => t.id === c.activeTabId) : undefined;
  const next = active && tabVisible(active, c.projectFilter) ? document.getElementById(agentTabDomId(active.id)) : null;
  (next ?? document.querySelector<HTMLElement>('[data-pane="left"]'))?.focus();
}

/** A clone of a live descriptor preserves its incarnation. Removal followed by
 * any new admission, even a reset reusing seq/id, creates another incarnation. */
export interface AgentPaneLease {
  readonly owner: WorkspaceOwnerSession;
  readonly tabId: string;
  readonly incarnation: number;
  readonly seq: number;
}
let incarnation = 0;
const leases = new Map<string, AgentPaneLease>();
const present = new Set<string>();
const closeWaits = new Set<AbortController>();
const closeToasts = new Map<number, ReturnType<typeof setTimeout>>();
function observeTabs(): void {
  const owner = workspaceOwnerSession();
  const tabs = useCompanion.getState().tabs;
  const ids = new Set(tabs.map((t) => t.id));
  for (const tab of tabs) {
    const old = leases.get(tab.id);
    if (!present.has(tab.id) || !old || old.owner !== owner || old.seq !== tab.seq) {
      leases.set(tab.id, { owner, tabId: tab.id, seq: tab.seq, incarnation: ++incarnation });
    }
  }
  for (const id of present) {
    if (!ids.has(id)) useAgentPaneStore.getState().setClosing(id, false);
  }
  present.clear();
  for (const id of ids) present.add(id);
}
useCompanion.subscribe(observeTabs);
observeTabs();
subscribeWorkspaceOwnerAdmission(({ session, state }) => {
  if (state === "suspended") return;
  if (state === "retiring" || state === "failed" || session.subject === null
      || [...leases.values()].some((lease) => lease.owner !== session)) {
    for (const wait of closeWaits) wait.abort();
    closeWaits.clear();
    for (const [id, timer] of closeToasts) { clearTimeout(timer); toast.dismiss(id); }
    closeToasts.clear();
    leases.clear(); present.clear();
    useAgentPaneStore.getState().reset();
  }
});

export function useAgentOwnerAdmission() {
  return useSyncExternalStore(subscribeWorkspaceOwnerAdmission, workspaceOwnerAdmission, workspaceOwnerAdmission);
}
export function captureAgentPaneLease(tabId: string): AgentPaneLease | null {
  const owner = workspaceOwnerSession();
  if (owner.subject === null) return null;
  const lease = leases.get(tabId);
  return lease?.owner === owner && present.has(tabId) ? lease : null;
}
export function isCurrentAgentPaneLease(lease: AgentPaneLease): boolean {
  return leases.get(lease.tabId) === lease && present.has(lease.tabId)
    && useCompanion.getState().tabs.some((tab) => tab.id === lease.tabId && tab.seq === lease.seq);
}

/** Same companion retirement/20-entry Undo policy, with an originating owner
 * and incarnation on this pane's deferred callbacks. No shared callback edits. */
function closeWithOwnedUndo(lease: AgentPaneLease, title?: string): void {
  const c = useCompanion.getState();
  const index = c.tabs.findIndex((t) => t.id === lease.tabId);
  if (index < 0) return;
  const tab = c.tabs[index];
  const wasActive = c.activeTabId === lease.tabId;
  c.closeAgentTab(tab.id);
  useCompanion.setState((st) => ({ retired: [...st.retired, { tab, index, wasActive }].slice(-20) }));
  const toastId = toast.undo(`Closed ${title ?? tab.title}. The agent itself is untouched.`, () => {
    const wait = new AbortController();
    closeWaits.add(wait);
    const restore = (ok: boolean) => {
      closeWaits.delete(wait);
      if (!ok || !isWorkspaceOwnerSession(lease.owner) || leases.get(tab.id) !== lease || present.has(tab.id)) return;
      useCompanion.getState().restoreAgentTab(tab, index, wasActive);
    };
    if (isConfirmedAgentOwner(lease.owner)) restore(true);
    else void awaitWorkspaceOwnerSession(lease.owner, wait.signal).then(restore);
  });
  closeToasts.set(toastId, setTimeout(() => closeToasts.delete(toastId), UNDO_TTL_MS));
}

/** 240 ms inert linger, then the existing 10 s Undo and focus return. */
export function closeAgentPane(tabId: string, title?: string): void {
  const lease = captureAgentPaneLease(tabId);
  if (!lease || !isWorkspaceOwnerSession(lease.owner)) return;
  const s = useAgentPaneStore.getState();
  if (s.closing[tabId]) return;
  s.setClosing(tabId, true);
  const wait = new AbortController();
  closeWaits.add(wait);
  setTimeout(() => {
    const complete = (ok: boolean) => {
      closeWaits.delete(wait);
      if (!ok || !isWorkspaceOwnerSession(lease.owner) || !isCurrentAgentPaneLease(lease)) return;
      useAgentPaneStore.getState().setClosing(tabId, false);
      closeWithOwnedUndo(lease, title);
      if (isWorkspaceOwnerSession(lease.owner)) returnFocusAfterClose();
    };
    if (isConfirmedAgentOwner(lease.owner)) complete(true);
    else void awaitWorkspaceOwnerSession(lease.owner, wait.signal).then(complete);
  }, CLOSE_LINGER_MS);
}

/** The one wire from the selection to the companion's project filter.
 *  Called by CompanionPane (both mounts; a second subscription writes the
 *  same value). While it is mounted the filter MIRRORS the selection: a
 *  store reset under it (auth.tsx resets the companion on an owner change)
 *  re-applies the selection instead of leaving the filter null, which would
 *  show every project's tabs until the next switch. */
export function useSyncProjectFilter(): void {
  useEffect(() => {
    const apply = () => {
      const projectId = useSelection.getState().selection.projectId;
      if (useCompanion.getState().projectFilter !== projectId) useCompanion.getState().setProjectFilter(projectId);
    };
    apply();
    const offSelection = useSelection.subscribe((s, p) => {
      if (s.selection.projectId !== p.selection.projectId) apply();
    });
    const offCompanion = useCompanion.subscribe((s, p) => {
      if (s.projectFilter === null && p.projectFilter !== null) apply();
    });
    return () => { offSelection(); offCompanion(); };
  }, []);
}
