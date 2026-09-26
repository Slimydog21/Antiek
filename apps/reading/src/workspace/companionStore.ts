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


export interface CompanionState {
  tabs: AgentTabDescriptor[];
  activeTabId: string | null;
  seq: number;
  /** Open (or focus) an agent's tab. Returns the stable id. In the docked
   *  preset, spawning an agent surfaces the companion panel — the pane must
   *  exist for the tab to be seen. */
  openAgentTab: (input: OpenAgentTabInput) => string;
  /** Remove the tab (the agent/thread is untouched — a view act). */
  closeAgentTab: (id: string) => void;
  activateAgentTab: (id: string) => void;
  /** Wrap-cycling for the prefix n/p keys (all tabs, overflow included). */
  cycleAgentTab: (direction: 1 | -1) => void;
  /** Test seam + preset hygiene. */
  reset: () => void;
}

export const useCompanion = create<CompanionState>()((set, get) => ({
  tabs: [],
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

  reset: () => set({ tabs: [], activeTabId: null, seq: 0 }),
}));
