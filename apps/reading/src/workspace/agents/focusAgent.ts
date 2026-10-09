/**
 * agents/focusAgent.ts — SPR-10: the ONE way a key, the picker's Enter and
 * a toast's "Open" land on an agent. Opens or focuses the companion tab,
 * moves pane focus to the right, and marks the run seen explicitly (so
 * done → idle happens here even when document.hasFocus() was false).
 * LAZY toward companionStore (the store ships with the lazy pane).
 */
import { useWorkspace } from "../WorkspaceStore";
import { COMPANION_PANEL_ID } from "../companionVisibility";

export interface FocusTarget {
  runId: string;
  viewId: string;
  viewOpen: boolean;
  investigationId?: string;
  title: string;
  kind: "research-thread" | "dialogue";
}

export function focusAgent(target: FocusTarget): Promise<void> {
  return import("../companionStore").then(({ useCompanion }) => {
    const c = useCompanion.getState();
    if (target.viewOpen && c.tabs.some((t) => t.id === target.viewId)) {
      c.activateAgentTab(target.viewId);
    } else {
      // openAgentTab dedups by the stable id and surfaces the companion in
      // the docked preset (companionStore.ts:158-175).
      c.openAgentTab({
        kind: target.kind,
        ...(target.investigationId !== undefined ? { investigationId: target.investigationId } : {}),
        title: target.title,
      });
    }
    const ws = useWorkspace.getState();
    ws.setFocusedPane("right");
    if (ws.panels[COMPANION_PANEL_ID]) ws.focus(COMPANION_PANEL_ID);
    return import("./agentStatusStore").then((m) => m.useAgentStatusStore.getState().markFocused(target.runId));
  });
}
