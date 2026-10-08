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
  const removed = [...present].filter((id) => !ids.has(id)).map((id) => ({ id, lease: leases.get(id) }));
  for (const tab of tabs) {
    const old = leases.get(tab.id);
    if (!present.has(tab.id) || !old || old.owner !== owner || old.seq !== tab.seq) {
      leases.set(tab.id, { owner, tabId: tab.id, seq: tab.seq, incarnation: ++incarnation });
    }
  }
  present.clear();
  for (const id of ids) present.add(id);
  // Commit membership before publishing a closing flag. A subscriber can
  // synchronously install a replacement, whose membership we must not erase.
  for (const { id, lease } of removed) {
    if (workspaceOwnerSession() === owner && leases.get(id) === lease && !present.has(id)) {
      useAgentPaneStore.getState().setClosing(id, false);
    }
  }
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
function closeWithOwnedUndo(lease: AgentPaneLease, title: string | undefined, wait: AbortController): void {
  if (!isConfirmedAgentOwner(lease.owner) || !isCurrentAgentPaneLease(lease)) { closeWaits.delete(wait); return; }
  const c = useCompanion.getState();
  const index = c.tabs.findIndex((t) => t.id === lease.tabId);
  if (index < 0) { closeWaits.delete(wait); return; }
  const tab = c.tabs[index];
  const wasActive = c.activeTabId === lease.tabId;
  const retired = { tab, index, wasActive };
  let retiredPublished = false;
  let returnedToastId: number | null = null;
  const stillClosed = () => {
    const a = workspaceOwnerAdmission();
    return a.session === lease.owner && a.state !== "retiring" && a.state !== "failed"
      && leases.get(tab.id) === lease && !present.has(tab.id)
      && !useCompanion.getState().tabs.some((t) => t.id === tab.id);
  };
  const discard = () => {
    closeWaits.delete(wait); wait.abort();
    if (returnedToastId !== null) {
      clearTimeout(closeToasts.get(returnedToastId)); closeToasts.delete(returnedToastId);
      toast.dismiss(returnedToastId);
    }
    if (retiredPublished) useCompanion.setState((s) => s.retired.includes(retired)
      ? { retired: s.retired.filter((entry) => entry !== retired) } : s);
  };
  const resume = (next: () => void) => {
    const admitted = (ok: boolean) => {
      if (!ok || wait.signal.aborted || !stillClosed()) { discard(); return; }
      if (!isConfirmedAgentOwner(lease.owner)) { resume(next); return; }
      try { next(); }
      catch (error) {
        try { discard(); }
        catch (cleanupError) { throw new AggregateError([error, cleanupError], "Agent close publication and owned cleanup failed"); }
        throw error;
      }
    };
    if (isConfirmedAgentOwner(lease.owner)) admitted(true);
    else void awaitWorkspaceOwnerSession(lease.owner, wait.signal).then(admitted);
  };
  try { c.closeAgentTab(tab.id); }
  catch (error) { closeWaits.delete(wait); wait.abort(); throw error; }
  resume(() => {
    retiredPublished = true;
    useCompanion.setState((st) => ({ retired: [...st.retired, retired].slice(-20) }));
    resume(() => {
      returnedToastId = toast.undo(`Closed ${title ?? tab.title}. The agent itself is untouched.`, () => {
        const restoreWait = new AbortController();
        closeWaits.add(restoreWait);
        const restore = (ok: boolean) => {
          closeWaits.delete(restoreWait);
          if (!ok || restoreWait.signal.aborted || !isConfirmedAgentOwner(lease.owner) || !stillClosed()) return;
          useCompanion.getState().restoreAgentTab(tab, index, wasActive);
        };
        if (isConfirmedAgentOwner(lease.owner)) restore(true);
        else void awaitWorkspaceOwnerSession(lease.owner, restoreWait.signal).then(restore);
      });
      // The emitter published synchronously before returning this ID. Retirement
      // there cannot be covered by the pre-call owner cleanup subscription.
      if (wait.signal.aborted || !stillClosed()) { discard(); return; }
      const toastId = returnedToastId;
      closeToasts.set(toastId, setTimeout(() => closeToasts.delete(toastId), UNDO_TTL_MS));
      resume(() => { closeWaits.delete(wait); returnFocusAfterClose(); });
    });
  });
}

/** 240 ms inert linger, then the existing 10 s Undo and focus return. */
export function closeAgentPane(tabId: string, title?: string): void {
  const lease = captureAgentPaneLease(tabId);
  if (!lease || !isWorkspaceOwnerSession(lease.owner)) return;
  const s = useAgentPaneStore.getState();
  if (s.closing[tabId]) return;
  const wait = new AbortController();
  closeWaits.add(wait);
  const current = () => {
    const a = workspaceOwnerAdmission();
    return !wait.signal.aborted && a.session === lease.owner && a.state !== "retiring" && a.state !== "failed" && isCurrentAgentPaneLease(lease);
  };
  const retire = () => { closeWaits.delete(wait); wait.abort(); };
  try { s.setClosing(tabId, true); }
  catch (error) { retire(); throw error; }
  if (!current()) { retire(); return; }
  setTimeout(() => {
    const complete = (ok: boolean) => {
      if (!ok || !current()) { retire(); return; }
      if (!isConfirmedAgentOwner(lease.owner)) { void awaitWorkspaceOwnerSession(lease.owner, wait.signal).then(complete); return; }
      try { useAgentPaneStore.getState().setClosing(tabId, false); }
      catch (error) { retire(); throw error; }
      const close = (admitted: boolean) => {
        if (!admitted || !current()) { retire(); return; }
        if (!isConfirmedAgentOwner(lease.owner)) { void awaitWorkspaceOwnerSession(lease.owner, wait.signal).then(close); return; }
        closeWithOwnedUndo(lease, title, wait);
      };
      if (isConfirmedAgentOwner(lease.owner)) close(true);
      else void awaitWorkspaceOwnerSession(lease.owner, wait.signal).then(close);
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
