/**
 * companionStore.ts — the companion right pane's agent tabs (cockpit C4).
 *
 * Research and imported durable nodes are projections of the lazy tab tree.
 * Commands delegate to that tree's allocation, CAS, close and restore path.
 * Re-opening a research reference focuses its opaque ID in this mode/project.
 * The single `agent:dialogue` is explicitly session-only. It has no durable
 * thread reference and never enters a server snapshot.
 * Tab semantics (ratified):
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
import { getTabOwner, subscribeTabOwner } from "./tabTreeOwner";
import type { ThoughtPartnerOnceReply } from "../components/ai/thoughtPartnerOnce";

export type AgentTabKind = "research-thread" | "dialogue" | "durable-thread" | "project-tool" | "writing-block";

interface AgentTabBase {
  id: string;
  title: string;
  /** The document the thread was born from, when the opening surface knew
   *  it — the cross-pane seam's payload (crossPane.ts). Absent when unknown:
   *  no "open source document" affordance, never a guessed one. */
  documentId?: string;
  /** Activation order. */
  seq: number;
}

export type AgentTabDescriptor = AgentTabBase & (
  | { kind: "research-thread"; investigationId: string; persistence: "tree"; publicNumber: number | null; threadKind: "research" }
  | { kind: "dialogue"; investigationId?: never; persistence: "session"; publicNumber?: never; threadKind?: never }
  | { kind: "durable-thread"; investigationId: string; persistence: "tree"; publicNumber: number | null; threadKind: "dialogue" | "reformat" | "diligence" | "island" }
  | { kind: "project-tool"; investigationId?: never; projectId: string; persistence: "tree"; publicNumber: number | null; threadKind?: never; toolKind: "findings" | "flags" }
  | { kind: "writing-block"; investigationId?: never; blockId: string; persistence: "tree"; publicNumber: number | null; threadKind?: never }
);

export type OpenAgentTabInput = {
  title?: string;
  documentId?: string;
} & ({ kind: "research-thread"; investigationId: string } | { kind: "dialogue"; investigationId?: never });

import { COMPANION_PANEL_ID } from "./companionVisibility";

export { COMPANION_PANEL_ID, companionVisible } from "./companionVisibility";

/** The prefix of a book's reading thread id, `read-<documentId>`. */
const READING_THREAD_PREFIX = "read-";

/** `read-` ids that name no document: a meta-reading asset
 *  (`read-meta-<asset>`), a reading session (`read-session-<id>`) and the
 *  passage-research default parent (`read-spin`). A child of one of these
 *  was not born from the document its suffix would spell. */
const NON_DOCUMENT_READ_PREFIXES = ["read-meta-", "read-session-"] as const;
const NON_DOCUMENT_READ_IDS: ReadonlySet<string> = new Set(["read-spin"]);

/**
 * The document a thread was born from, or null when that is not known.
 *
 * 1. `document_id` on the summary (THREAD-CONTRACT §1.2 ThreadSummary,
 *    from the event envelope; lane B's W1 wire) when it is set.
 * 2. Otherwise an exact `read-<documentId>` parent: a thread hung under a
 *    book's reading thread. The `read-` ids that name no document (above)
 *    are refused.
 * 3. Otherwise null, and the pane offers no "open source document", never a
 *    guessed one.
 *
 * Research spun from a book (POST /books/{id}/spin-research) carries no
 * parent today, so it reaches branch 1 only once lane B ships `document_id`.
 */
export function sourceDocumentOf(
  summary: { document_id?: string | null; parent_investigation_id?: string | null } | undefined,
): string | null {
  if (!summary) return null;
  const direct = summary.document_id?.trim();
  if (direct) return direct;
  const parent = summary.parent_investigation_id?.trim();
  if (!parent?.startsWith(READING_THREAD_PREFIX)) return null;
  if (NON_DOCUMENT_READ_IDS.has(parent)) return null;
  if (NON_DOCUMENT_READ_PREFIXES.some((p) => parent.startsWith(p))) return null;
  return parent.slice(READING_THREAD_PREFIX.length).trim() || null;
}

/** Installed by the lazy tree store. Durable tabs are a projection, never
 * a second persistence authority in this entry-chunk store. */
export interface CompanionTreePort {
  open: (input: OpenAgentTabInput) => string;
  activate: (id: string) => void;
  close: (id: string) => void;
  restore: (id: string) => boolean;
  reopen: () => boolean;
  owns: (id: string) => boolean;
}
let treePort: CompanionTreePort | null = null;
export function setCompanionTreePort(port: CompanionTreePort): void { treePort = port; }

export interface DialogueDraft {
  prompt: string;
  pending: boolean;
  exchange: ThoughtPartnerOnceReply | null;
  failure: { reason: string | null } | null;
}
const emptyDialogue = (): DialogueDraft => ({ prompt: "", pending: false, exchange: null, failure: null });


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
  dialogue: DialogueDraft;
  setDialogue: (patch: Partial<DialogueDraft>) => void;
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
  dialogue: emptyDialogue(),
  setDialogue: (patch) => set((s) => ({ dialogue: { ...s.dialogue, ...patch } })),

  openAgentTab: (input) => {
    if (input.kind === "research-thread") {
      if (!treePort) return "";
      const id = treePort.open(input);
      if (id) {
        const ws = useWorkspace.getState();
        if (ws.layoutPreset === "docked" && !ws.panels[COMPANION_PANEL_ID]) ws.open("Companion", {}, { mode: "docked-right", id: COMPANION_PANEL_ID, title: "Companion" });
      }
      return id;
    }
    const id = "agent:dialogue";
    const existing = get().tabs.find((t) => t.id === id);
    if (existing) {
      set({ activeTabId: id });
    } else {
      const seq = get().seq + 1;
      const base: AgentTabBase = {
        id,
        title:
          input.title?.trim() ||
          "dialogue",
        documentId: input.documentId,
        seq,
      };
      const tab: AgentTabDescriptor = { ...base, kind: "dialogue", persistence: "session" };
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

  closeAgentTab: (id) => {
    if (treePort?.owns(id)) { treePort.close(id); return; }
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
    });
  },

  restoreAgentTab: (tab, index, activate) => {
    if (tab.persistence === "tree") { treePort?.restore(tab.id); return; }
    set((s) => {
      if (s.tabs.some((t) => t.id === tab.id)) return s;
      const tabs = [...s.tabs];
      tabs.splice(Math.max(0, Math.min(index, tabs.length)), 0, tab);
      return { tabs, activeTabId: activate ? tab.id : s.activeTabId };
    });
  },

  activateAgentTab: (id) => {
    if (!get().tabs.some((t) => t.id === id)) return;
    set({ activeTabId: id });
    if (treePort?.owns(id)) treePort.activate(id);
  },

  cycleAgentTab: (direction) => {
      const s = get();
      if (s.tabs.length === 0) return;
      const cur = s.activeTabId
        ? s.tabs.findIndex((t) => t.id === s.activeTabId)
        : -1;
      const next = (cur + direction + s.tabs.length) % s.tabs.length;
      s.activateAgentTab(s.tabs[next].id);
  },

  closeAgentTabWithUndo: (id, title) => {
    const s = get();
    const index = s.tabs.findIndex((t) => t.id === id);
    if (index === -1) return;
    const tab = s.tabs[index];
    if (treePort?.owns(id)) { treePort.close(id); return; }
    const wasActive = s.activeTabId === id;
    const ownerEpoch = getTabOwner().epoch;
    s.closeAgentTab(id);
    set((st) => ({ retired: [...st.retired, { tab, index, wasActive }].slice(-RETIRED_AGENT_TABS_KEPT) }));
    toast.undo(`Closed ${title ?? tab.title}. The agent itself is untouched.`, () => {
      if (getTabOwner().epoch === ownerEpoch) get().restoreAgentTab(tab, index, wasActive);
    });
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
      return treePort?.reopen() ?? false;
    }
    const { tab, index } = retired[at];
    set({ retired: retired.slice(0, at) });
    // Reopening is a request to see it, whether or not it was active.
    get().restoreAgentTab(tab, index, true);
    return true;
  },

  reset: () => set({ tabs: [], retired: [], activeTabId: null, seq: 0, dialogue: emptyDialogue() }),
}));

let ownerEpoch = getTabOwner().epoch;
subscribeTabOwner(() => {
  if (ownerEpoch === getTabOwner().epoch) return;
  ownerEpoch = getTabOwner().epoch;
  useCompanion.getState().reset();
});
