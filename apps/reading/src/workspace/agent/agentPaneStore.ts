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
import { useEffect } from "react";
import { create } from "zustand";

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

/** "Close" is the agent TAB (10 s undo) after a 240 ms inert linger on the
 *  surface; the inset column never collapses (decision 5). Idempotent while
 *  the linger runs. */
export function closeAgentPane(tabId: string, title?: string): void {
  const s = useAgentPaneStore.getState();
  if (s.closing[tabId]) return;
  s.setClosing(tabId, true);
  setTimeout(() => {
    useAgentPaneStore.getState().setClosing(tabId, false);
    useCompanion.getState().closeAgentTabWithUndo(tabId, title);
    returnFocusAfterClose();
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
