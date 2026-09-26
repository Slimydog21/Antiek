/**
 * companionStore.ts — the companion right pane's agent tabs (cockpit C4).
 *
 * One agent = one tab. Tab semantics (ratified):
 *   - stable per-agent ids: re-activating an existing agent FOCUSES its tab,
 *     never duplicates (a research thread is `agent:thread:<investigationId>`;
 *     the dialogue agent is the single `agent:dialogue` — it is one-shot, so
 *     one instance is the honest model);
 *   - close removes the TAB only — the agent/thread it pointed at is
 *     untouched (closing is a view act, never a lifecycle act);
 *   - tab order is activation order (a monotonic seq, never renumbered);
 *   - cycling (the prefix n/p keys) wraps across ALL tabs — visual overflow
 *     (the ⋯ menu) is never a hopping boundary.
 *
 * The pane's presence rule per preset lives here too, so the key handlers
 * share it: in the omarchy-inset preset the right pane IS the companion
 * (always visible); in the docked preset the companion is the "Companion"
 * right-dock panel — visible iff that panel is open.
 */
import { create } from "zustand";

import { toast } from "../components/lemon/LemonToast";
import { useWorkspace } from "./WorkspaceStore";

export type AgentTabKind = "research-thread" | "dialogue";

export interface AgentTabDescriptor {
  id: string;
  kind: AgentTabKind;
  title: string;
  /** research-thread tabs: the thread they watch. */
  investigationId?: string;
  /** The document the thread was born from, when the opening surface knew
   *  it — the cross-pane seam's payload (crossPane.ts). Absent when unknown:
   *  no "open source document" affordance, never a guessed one. */
  documentId?: string;
  /** Activation order. */
  seq: number;
}

export interface OpenAgentTabInput {
  kind: AgentTabKind;
  title?: string;
  investigationId?: string;
  documentId?: string;
}

import { COMPANION_PANEL_ID } from "./companionVisibility";

export { COMPANION_PANEL_ID, companionVisible } from "./companionVisibility";

function agentTabId(input: OpenAgentTabInput): string {
  if (input.kind === "research-thread") {
    return `agent:thread:${input.investigationId ?? ""}`;
  }
  return "agent:dialogue";
}


/** A closed agent tab, kept so it can come back where it was. */
export interface RetiredAgentTab {
  tab: AgentTabDescriptor;
  index: number;
  wasActive: boolean;
}

/** How many closed agent tabs prefix+shift+t can walk back through. */
const RETIRED_AGENT_TABS_KEPT = 20;

export interface CompanionState {
  tabs: AgentTabDescriptor[];
  /** Closed agent tabs, most recent last (session-scoped: agent tabs are a
   *  view, and the agents themselves outlive every close). */
  retired: RetiredAgentTab[];
  activeTabId: string | null;
  seq: number;
  /** Open (or focus) an agent's tab. Returns the stable id. In the docked
   *  preset, spawning an agent surfaces the companion panel — the pane must
   *  exist for the tab to be seen. */
  openAgentTab: (input: OpenAgentTabInput) => string;
  /** Remove the tab (the agent/thread is untouched — a view act). */
  closeAgentTab: (id: string) => void;
  /** Put a closed tab back where it was (its toast's Undo). A tab opened
   *  again meanwhile is left as it is. */
  restoreAgentTab: (tab: AgentTabDescriptor, index: number, activate: boolean) => void;
  activateAgentTab: (id: string) => void;
  /** Wrap-cycling for the prefix n/p keys (all tabs, overflow included). */
  cycleAgentTab: (direction: 1 | -1) => void;
  /** Close a tab behind the shared 10 s Undo (the × button, Delete, and
   *  prefix+shift+x with the right pane focused). `title` is what the toast
   *  names it (a thread's question when the caller knows it). */
  closeAgentTabWithUndo: (id: string, title?: string) => void;
  /** prefix+shift+x on the right pane: the active tab. False = none. */
  closeActiveAgentTab: () => boolean;
  /** prefix+shift+t on the right pane: the most recently closed tab that is
   *  not open again goes back in its place, active. False = none. */
  reopenLastClosedAgentTab: () => boolean;
  /** Test seam + preset hygiene. */
  reset: () => void;
}

export const useCompanion = create<CompanionState>()((set, get) => ({
  tabs: [],
  retired: [],
  activeTabId: null,
  seq: 0,

  openAgentTab: (input) => {
    const id = agentTabId(input);
    const existing = get().tabs.find((t) => t.id === id);
    if (existing) {
      set({ activeTabId: id });
    } else {
      const seq = get().seq + 1;
      const tab: AgentTabDescriptor = {
        id,
        kind: input.kind,
        title:
          input.title?.trim() ||
          (input.kind === "research-thread" ? "research" : "dialogue"),
        investigationId: input.investigationId,
        documentId: input.documentId,
        seq,
      };
      set((s) => ({ tabs: [...s.tabs, tab], activeTabId: id, seq }));
    }
    // The docked-preset mount: the companion is a right-dock panel; spawning
    // an agent surfaces it (closing it later is the operator's view act).
    const ws = useWorkspace.getState();
    if (ws.layoutPreset === "docked" && !ws.panels[COMPANION_PANEL_ID]) {
      ws.open("Companion", {}, { mode: "docked-right", id: COMPANION_PANEL_ID, title: "Companion" });
    }
    return id;
  },

  closeAgentTab: (id) =>
    set((s) => {
      const idx = s.tabs.findIndex((t) => t.id === id);
      if (idx === -1) return s;
      const tabs = s.tabs.filter((t) => t.id !== id);
      let activeTabId = s.activeTabId;
      if (activeTabId === id) {
        // Fall to the previous tab in activation order, else the next,
        // else nothing — the pane's honest empty state.
        activeTabId = tabs[idx - 1]?.id ?? tabs[idx]?.id ?? null;
      }
      return { tabs, activeTabId };
    }),

  restoreAgentTab: (tab, index, activate) =>
    set((s) => {
      if (s.tabs.some((t) => t.id === tab.id)) return s;
      const tabs = [...s.tabs];
      tabs.splice(Math.max(0, Math.min(index, tabs.length)), 0, tab);
      return { tabs, activeTabId: activate ? tab.id : s.activeTabId };
    }),

  activateAgentTab: (id) =>
    set((s) => (s.tabs.some((t) => t.id === id) ? { activeTabId: id } : s)),

  cycleAgentTab: (direction) =>
    set((s) => {
      if (s.tabs.length === 0) return s;
      const cur = s.activeTabId
        ? s.tabs.findIndex((t) => t.id === s.activeTabId)
        : -1;
      const next = (cur + direction + s.tabs.length) % s.tabs.length;
      return { activeTabId: s.tabs[next].id };
    }),

  closeAgentTabWithUndo: (id, title) => {
    const s = get();
    const index = s.tabs.findIndex((t) => t.id === id);
    if (index === -1) return;
    const tab = s.tabs[index];
    const wasActive = s.activeTabId === id;
    s.closeAgentTab(id);
    set((st) => ({ retired: [...st.retired, { tab, index, wasActive }].slice(-RETIRED_AGENT_TABS_KEPT) }));
    toast.undo(`Closed ${title ?? tab.title}. The agent itself is untouched.`, () =>
      get().restoreAgentTab(tab, index, wasActive),
    );
  },

  closeActiveAgentTab: () => {
    const id = get().activeTabId;
    if (!id) return false;
    get().closeAgentTabWithUndo(id);
    return true;
  },

  reopenLastClosedAgentTab: () => {
    const open = new Set(get().tabs.map((t) => t.id));
    const retired = get().retired;
    // A tab reopened meanwhile (its toast's Undo, or opened again) is skipped.
    let at = retired.length - 1;
    while (at >= 0 && open.has(retired[at].tab.id)) at--;
    if (at < 0) {
      if (retired.length > 0) set({ retired: [] });
      return false;
    }
    const { tab, index } = retired[at];
    set({ retired: retired.slice(0, at) });
    // Reopening is a request to see it, whether or not it was active.
    get().restoreAgentTab(tab, index, true);
    return true;
  },

  reset: () => set({ tabs: [], retired: [], activeTabId: null, seq: 0 }),
}));
